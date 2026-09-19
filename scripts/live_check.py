"""Opt-in live provider smoke test. Uses an isolated temporary wardrobe, no messaging."""
import argparse
import asyncio
import base64
import json
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from hem.ai import AI
from hem.assistant import Assistant
from hem.sources import import_feed
from hem.store import Store
from hem.weather import Weather

ROOT = Path(__file__).resolve().parents[1]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--photo', type=Path)
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    ai = AI()
    forecast = await Weather().forecast(43.65, -79.38)
    print('Live weather OK:', forecast['date'])
    with tempfile.TemporaryDirectory(dir=ROOT / 'data', prefix='live-check-') as temp:
        store = Store(Path(temp) / 'check.sqlite3')
        assistant = Assistant(store, ai=ai)
        for item in ('top: navy wool sweater', 'bottom: charcoal trousers', 'shoes: black waterproof boots'):
            await assistant.reply('smoke', 'add ' + item)
        await assistant.reply('smoke', 'location 43.65,-79.38 Toronto')
        import_feed(store, 'smoke', '<rss><channel><item><title>Synthetic office layering fixture</title>'
                    '<link>https://example.com/office-layers</link>'
                    '<description>Pair a navy sweater with charcoal trousers for office layering.</description>'
                    '</item></channel></rss>', 'https://example.com/feed')
        reply = await assistant.reply('smoke', 'Pick an outfit for the office using the imported office layering source. Cite it if relevant.')
        assert 'Outfit ' in reply and 'Sources:' in reply, 'Live advice failed ownership/source validation'
        assert not store.snapshot('smoke')['wears']
        print('Live outfit advice, wardrobe validation and source citations OK.')
        followup = await assistant.reply('smoke', 'Why does that combination work?')
        assert 'temporarily unavailable' not in followup and 'could not complete' not in followup
        print('Live conversational follow-up OK.')
        if args.photo:
            suffix = args.photo.suffix.lower()
            mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}[suffix]
            image = f'data:{mime};base64,' + base64.b64encode(args.photo.read_bytes()).decode()
            reply = await assistant.reply('smoke-photo', 'Identify the visible clothes in this wardrobe photo.', [image])
            with store.connect() as db:
                draft = db.execute('SELECT id,garments FROM photo_drafts WHERE user_id=?', ('smoke-photo',)).fetchone()
            assert draft and json.loads(draft['garments']), 'No live garment draft created'
            assert not store.snapshot('smoke-photo')['wardrobe']
            await assistant.reply('smoke-photo', 'confirm photo ' + draft['id'])
            print('Live photo recognition and confirmation OK:', len(store.snapshot('smoke-photo')['wardrobe']), 'garments')


if __name__ == '__main__':
    asyncio.run(main())
