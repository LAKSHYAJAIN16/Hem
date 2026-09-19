import asyncio
import base64
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import ParseError

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from hem.assistant import Assistant
from hem.linq import inbound, send_reply, verify
from hem.sources import import_feed
from hem.store import Store

load_dotenv(Path(__file__).resolve().parents[3] / '.env')
logger = logging.getLogger(__name__)


def create_app(database=None, assistant=None):
    store = Store(database or os.getenv('HEM_DATABASE', 'data/hem.sqlite3'))
    engine = assistant or Assistant(store)
    wake = asyncio.Event()

    async def process_inbox():
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            event = db.execute("SELECT * FROM inbox WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not event:
                return False
            db.execute("UPDATE inbox SET status='processing' WHERE id=?", (event['id'],))
        message = json.loads(event['payload'])
        try:
            if message['has_media'] and not message['images'] and not message['text']:
                reply = 'Please send a JPEG, PNG or WebP wardrobe photo.'
            else:
                reply = await engine.reply(message['user_id'], message['text'], message['images'], request_id=event['id'])
            status = 'pending' if os.getenv('HEM_SEND_MESSAGES', 'false').lower() == 'true' else 'dry_run'
            with store.connect() as db:
                db.execute('INSERT OR IGNORE INTO events(id,message_id,user_id,chat_id,reply,status) VALUES(?,?,?,?,?,?)',
                           (event['id'], message['message_id'], message['user_id'], message['chat_id'], reply, status))
                db.execute("UPDATE inbox SET status='done',payload='{}' WHERE id=?", (event['id'],))
        except Exception as exc:
            logger.error('Inbox processing failed: %s', type(exc).__name__)
            with store.connect() as db:
                db.execute("UPDATE inbox SET status='failed' WHERE id=?", (event['id'],))
        return True

    async def receive_worker():
        while True:
            wake.clear()
            if await process_inbox():
                continue
            try:
                await asyncio.wait_for(wake.wait(), timeout=1)
            except TimeoutError:
                pass

    async def deliver_outbox():
        while True:
            if os.getenv('HEM_SEND_MESSAGES', 'false').lower() == 'true' and os.getenv('LINQ_API_KEY'):
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    event = db.execute("SELECT * FROM events WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
                    if event:
                        db.execute("UPDATE events SET status='sending' WHERE id=?", (event['id'],))
                if event:
                    try:
                        await send_reply(os.environ['LINQ_API_KEY'], event['chat_id'], event['reply'])
                        status = 'sent'
                    except Exception:
                        status = 'needs_review'
                    with store.connect() as db:
                        db.execute('UPDATE events SET status=? WHERE id=?', (status, event['id']))
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        with store.connect() as db:
            db.execute("UPDATE events SET status='needs_review' WHERE status='sending'")
            db.execute("UPDATE inbox SET status='queued' WHERE status='processing'")
        workers = [asyncio.create_task(receive_worker()), asyncio.create_task(deliver_outbox())]
        yield
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    app = FastAPI(title='Hem', description='Your wardrobe. Your taste. Your next outfit.', lifespan=lifespan)
    app.state.store = store
    app.state.assistant = engine
    app.state.process_inbox = process_inbox

    @app.middleware('http')
    async def body_limit(request, call_next):
        limit = 1_000_000 if request.url.path == '/webhooks/linq' else 8_500_000
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                return Response('Request too large', status_code=413)
        request._body = bytes(body)
        return await call_next(request)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'Hem', 'ai_configured': engine.ai.configured,
                'live_sending': os.getenv('HEM_SEND_MESSAGES', 'false').lower() == 'true'}

    @app.post('/webhooks/linq', status_code=202)
    async def webhook(request: Request):
        secret = os.getenv('LINQ_WEBHOOK_SECRET', '')
        if not secret:
            raise HTTPException(503, 'Configure the webhook signing secret.')
        body = await request.body()
        if not verify(secret, body, request.headers):
            raise HTTPException(401, 'Invalid webhook signature or timestamp.')
        try:
            payload = json.loads(body)
            event_id = payload['event_id']
            if not isinstance(event_id, str) or event_id != request.headers['webhook-id']:
                raise ValueError('Event ID mismatch')
            message = inbound(payload)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(400, 'Invalid Linq V3 event.')
        if message is None:
            return Response(content='{"status":"ignored"}', media_type='application/json')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            duplicate = db.execute('SELECT id FROM events WHERE id=? OR message_id=?', (event_id, message['message_id'])).fetchone()
            duplicate = duplicate or db.execute('SELECT id FROM inbox WHERE id=? OR message_id=?', (event_id, message['message_id'])).fetchone()
            if duplicate:
                return {'status': 'duplicate'}
            db.execute('INSERT INTO inbox(id,message_id,payload) VALUES(?,?,?)', (event_id, message['message_id'], json.dumps(message)))
        wake.set()
        return {'status': 'queued'}

    def authorize(request: Request):
        token = os.getenv('HEM_DEV_TOKEN', '')
        provided = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not token or not hmac.compare_digest(token, provided):
            raise HTTPException(403, 'A local development token is required.')

    class DevMessage(BaseModel):
        user_id: str = Field(min_length=1, max_length=100)
        text: str = Field(default='', max_length=4000)
        images: list[str] = Field(default_factory=list, max_length=2)
        occasion: str = Field(default='', max_length=200)
        on_date: date | None = None

    @app.post('/dev/chat', dependencies=[Depends(authorize)])
    async def simulate(body: DevMessage):
        if not body.text.strip() and not body.images:
            raise HTTPException(422, 'Provide a message or photo.')
        return {'reply': await engine.reply('dev:' + body.user_id, body.text, body.images,
                                           occasion=body.occasion, on_date=body.on_date)}

    class FeedImport(BaseModel):
        user_id: str = Field(min_length=1, max_length=100)
        source_url: str = Field(max_length=2000)
        xml: str = Field(max_length=2_000_000)

    @app.post('/dev/sources/import', dependencies=[Depends(authorize)])
    def import_sources(body: FeedImport):
        try:
            count = import_feed(store, 'dev:' + body.user_id, body.xml, body.source_url)
        except (ValueError, ParseError) as exc:
            raise HTTPException(422, 'Provide a valid RSS/Atom document and original HTTPS feed URL.') from exc
        return {'imported': count}

    @app.get('/dev/wardrobe/{user_id}', dependencies=[Depends(authorize)])
    def wardrobe(user_id: str):
        snapshot = store.snapshot('dev:' + user_id)
        for outfit in snapshot['outfits']:
            outfit['item_ids'] = json.loads(outfit['item_ids'])
        for detail in snapshot['details']:
            detail['attributes'] = json.loads(detail['attributes'])
        return snapshot

    @app.get('/dev/photos/{user_id}/{asset_id}', dependencies=[Depends(authorize)])
    def photo_asset(user_id: str, asset_id: str):
        with store.connect() as db:
            asset = db.execute('SELECT image FROM photo_assets WHERE id=? AND user_id=?', (asset_id, 'dev:' + user_id)).fetchone()
        if not asset:
            raise HTTPException(404, 'Photo not found.')
        prefix, encoded = asset['image'].split(',', 1)
        return Response(base64.b64decode(encoded), media_type=prefix[5:].split(';')[0],
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    return app
