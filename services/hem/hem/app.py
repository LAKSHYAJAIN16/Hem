import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from hem.linq import inbound, send_reply, verify
from hem.store import Store
from hem.stylist import chat, respond


load_dotenv(Path(__file__).resolve().parents[3] / '.env')


def create_app(database=None):
    store = Store(database or os.getenv('HEM_DATABASE', 'data/hem.sqlite3'))

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
                        # A timeout may follow an accepted send. Do not blindly send twice.
                        status = 'needs_review'
                    with store.connect() as db:
                        db.execute('UPDATE events SET status=? WHERE id=?', (status, event['id']))
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        # A crash during send has uncertain delivery; preserve it for review.
        with store.connect() as db:
            db.execute("UPDATE events SET status='needs_review' WHERE status='sending'")
        worker = asyncio.create_task(deliver_outbox())
        yield
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    app = FastAPI(title='Hem', description='Your wardrobe. Your taste. Your next outfit.', lifespan=lifespan)
    app.state.store = store

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'Hem', 'live_sending': os.getenv('HEM_SEND_MESSAGES', 'false').lower() == 'true'}

    @app.post('/webhooks/linq')
    async def webhook(request: Request):
        secret = os.getenv('LINQ_WEBHOOK_SECRET', '')
        if not secret:
            raise HTTPException(503, 'Set LINQ_WEBHOOK_SECRET before accepting webhooks.')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024 * 1024:
                raise HTTPException(413, 'Webhook too large.')
        if not verify(secret, bytes(body), request.headers):
            raise HTTPException(401, 'Invalid webhook signature or timestamp.')
        try:
            payload = json.loads(body)
            event_id = payload['event_id']
            if event_id != request.headers['webhook-id']:
                raise ValueError('Event ID mismatch')
            message = inbound(payload)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(400, 'Invalid Linq V3 event.')
        if message is None:
            return {'status': 'ignored'}
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            duplicate = db.execute('SELECT id FROM events WHERE id=? OR message_id=?', (event_id, message['message_id'])).fetchone()
            if duplicate:
                return {'status': 'duplicate'}
            if message['has_media'] and not message['text'].strip():
                reply = "Photo understanding isn't connected yet. Describe the item with 'add top: cream sweater' and I'll remember it."
            else:
                reply = respond(db, message['user_id'], message['text'])
            status = 'pending' if os.getenv('HEM_SEND_MESSAGES', 'false').lower() == 'true' else 'dry_run'
            db.execute('INSERT INTO events(id,message_id,user_id,chat_id,reply,status) VALUES(?,?,?,?,?,?)',
                       (event_id, message['message_id'], message['user_id'], message['chat_id'], reply, status))
        return {'status': status}

    class DevMessage(BaseModel):
        user_id: str = Field(min_length=1, max_length=100)
        text: str = Field(min_length=1, max_length=4000)

    @app.post('/dev/chat')
    def simulate(body: DevMessage, request: Request):
        token = os.getenv('HEM_DEV_TOKEN', '')
        provided = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not token or not hmac.compare_digest(token, provided):
            raise HTTPException(403, 'The local simulator requires HEM_DEV_TOKEN.')
        return {'reply': chat(store, 'dev:' + body.user_id, body.text)}

    return app
