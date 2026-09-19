import asyncio
import base64
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from hem.ai import AI, AIUnavailable, Advice, Garment, PhotoResult
from hem.app import create_app
from hem.assistant import Assistant
from hem.media import load_image, validate_image
from hem.sources import import_feed, fetch_feed
from hem.weather import Weather
from hem.store import Store

IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()


def run(awaitable):
    return asyncio.run(awaitable)


class FakeAI:
    configured = True
    def __init__(self):
        self.context = None
        self.advice = Advice(answer='Try your sweater with trousers.', item_ids=[], source_ids=[])
        self.photo_calls = 0

    async def describe(self, images, caption):
        self.photo_calls += 1
        return PhotoResult(garments=[Garment(category='top', description='navy sweater', colors=['navy'],
            material='unknown', pattern='solid', formality='casual', warmth='warm', confidence=0.9),
            Garment(category='bottom', description='blue trousers', colors=['blue'],
            material='unknown', pattern='solid', formality='smart-casual', warmth='medium', confidence=0.8)],
            notes='Please confirm these visible garments.')

    async def advise(self, context):
        self.context = context
        return self.advice


class FakeWeather:
    async def locate(self, name):
        return [{'latitude': 43.6, 'longitude': -79.4, 'label': 'Toronto'}]

    async def forecast(self, latitude, longitude, day=None):
        return {'date': day or '2026-09-19', 'low_c': 6, 'high_c': 10, 'feels_like_low_c': 4,
                'rain_chance': 80, 'timezone': 'America/Toronto', 'source_url': 'https://open-meteo.com/'}


def test_multi_garment_photo_requires_confirmation_and_is_idempotent(tmp_path):
    store = Store(tmp_path / 'hem.db')
    ai = FakeAI()
    engine = Assistant(store, ai=ai)
    reply = run(engine.reply('alice', 'my wardrobe', [IMAGE], request_id='photo-event'))
    draft = re.search(r'Photo ([a-f0-9]{10})', reply)[1]
    assert len(store.snapshot('alice')['wardrobe']) == 0
    assert '1. navy sweater' in reply and '2. blue trousers' in reply
    assert run(engine.reply('alice', 'my wardrobe', [IMAGE], request_id='photo-event')) == reply
    assert ai.photo_calls == 1
    assert 'not in' in run(engine.reply('bob', f'confirm photo {draft}'))
    assert 'Updated' in run(engine.reply('alice', f'edit photo {draft} 1 top: charcoal sweater'))
    run(engine.reply('alice', f'confirm photo {draft} 1', request_id='confirm-event'))
    assert [g['description'] for g in store.snapshot('alice')['wardrobe']] == ['charcoal sweater']
    run(engine.reply('alice', f'confirm photo {draft}'))
    assert len(store.snapshot('alice')['wardrobe']) == 1
    assert not store.snapshot('alice')['wears']


def test_advice_uses_owned_items_weather_sources_and_context(tmp_path):
    store = Store(tmp_path / 'hem.db')
    ai = FakeAI()
    engine = Assistant(store, ai=ai, weather=FakeWeather())
    for item in ('top: navy sweater', 'bottom: blue trousers', 'shoes: waterproof boots'):
        run(engine.reply('alice', 'add ' + item))
    run(engine.reply('alice', 'location Toronto'))
    feed = '<rss><channel><item><title>Office layers</title><link>https://style.test/layers</link><description>Wear a navy sweater with trousers for the office.</description></item></channel></rss>'
    assert import_feed(store, 'alice', feed, 'https://style.test/feed') == 1
    with store.connect() as db:
        source_id = db.execute('SELECT id FROM source_documents').fetchone()[0]
    ids = [g['id'] for g in store.snapshot('alice')['wardrobe']]
    ai.advice = Advice(answer='These layers suit a cool office day.', item_ids=ids, source_ids=[source_id])
    reply = run(engine.reply('alice', 'What should I wear to the office tomorrow?'))
    assert 'https://style.test/layers' in reply
    assert '2026-09-20' in reply and '80%' in reply
    assert ai.context['weather']['date'] == '2026-09-20'
    assert len(ai.context['available_wardrobe']) == 3
    assert not store.snapshot('alice')['wears']
    run(engine.reply('alice', 'wore it'))
    assert len(store.snapshot('alice')['wears']) == 1
    ai.advice = Advice(answer='A simpler variation could work.', item_ids=[], source_ids=[])
    run(engine.reply('alice', 'Make it less formal'))
    assert any('office tomorrow' in turn['content'] for turn in ai.context['conversation'])
    run(engine.reply('bob', 'office layers'))
    assert ai.context['sources'] == [] and ai.context['available_wardrobe'] == []


def test_invalid_model_ids_and_citations_never_persist(tmp_path):
    store = Store(tmp_path / 'hem.db')
    ai = FakeAI()
    engine = Assistant(store, ai=ai)
    for item in ('top: shirt', 'bottom: trousers', 'shoes: boots'):
        run(engine.reply('a', 'add ' + item))
    ids = [g['id'] for g in store.snapshot('a')['wardrobe']]
    run(engine.reply('a', 'laundry ' + ids[0]))
    ai.advice = Advice(answer='A suggestion', item_ids=ids, source_ids=[])
    reply = run(engine.reply('a', 'outfit'))
    assert 'rule-based' in reply
    assert not store.snapshot('a')['outfits']
    ai.advice = Advice(answer='A suggestion', item_ids=[], source_ids=['invented'])
    reply = run(engine.reply('a', 'advice'))
    assert 'Sources:' not in reply
    assert not store.snapshot('a')['outfits']


def test_rule_based_occasion_weather_ranking(tmp_path):
    store = Store(tmp_path / 'hem.db')
    engine = Assistant(store, ai=AI(api_key='', model=''), weather=FakeWeather())
    for item in ('top: tank', 'top: wool sweater', 'bottom: shorts', 'bottom: trousers',
                 'shoes: sandals', 'shoes: waterproof boots', 'outerwear: raincoat'):
        run(engine.reply('a', 'add ' + item))
    run(engine.reply('a', 'location Toronto'))
    reply = run(engine.reply('a', 'What should I wear to the office?'))
    assert all(word in reply for word in ('wool sweater', 'trousers', 'waterproof boots', 'raincoat'))


def test_automatic_care_requests_and_explicit_completion(tmp_path):
    store = Store(tmp_path / 'hem.db')
    engine = Assistant(store, ai=AI(api_key='', model=''))
    for item in ('top: sweater', 'bottom: trousers', 'shoes: boots'):
        run(engine.reply('a', 'add ' + item))
    garment = store.snapshot('a')['wardrobe'][0]['id']
    run(engine.reply('a', f'care {garment}: dryclean every 1 wear'))
    run(engine.reply('a', 'outfit'))
    assert 'Prepared dryclean request' in run(engine.reply('a', 'wore it'))
    run(engine.reply('a', 'wore it'))
    with store.connect() as db:
        request = db.execute('SELECT * FROM action_requests').fetchone()
        assert db.execute('SELECT count(*) FROM action_requests').fetchone()[0] == 1
        assert db.execute('SELECT wears_since_clean FROM care_rules').fetchone()[0] == 1
    assert 'not yours' in run(engine.reply('b', f"approve request {request['id']}"))
    assert 'Approve' in run(engine.reply('a', f"complete request {request['id']}"))
    run(engine.reply('a', 'laundry ' + garment))
    assert 'No booking' in run(engine.reply('a', f"approve request {request['id']}"))
    assert store.snapshot('a')['wardrobe'][0]['available'] == 0
    run(engine.reply('a', f"complete request {request['id']}"))
    assert store.snapshot('a')['wardrobe'][0]['available'] == 1
    run(engine.reply('a', 'auto order: boots size 9 under CAD 150'))
    with store.connect() as db:
        assert db.execute("SELECT status FROM action_requests WHERE kind='order'").fetchone()[0] == 'draft'


def test_ai_wire_format_and_refusal():
    def handle(request):
        data = json.loads(request.content)
        assert data['store'] is False
        assert data['text']['format']['strict'] is True
        assert data['input'][0]['content'][1]['type'] == 'input_image'
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': '{"garments":[],"notes":"No clothes visible."}'}]}]})
    ai = AI('test-key', 'test-model', transport=httpx.MockTransport(handle))
    assert run(ai.describe([IMAGE], 'wardrobe')).garments == []
    refusing = AI('test-key', 'test-model', transport=httpx.MockTransport(lambda r:
        httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]})))
    with pytest.raises(AIUnavailable):
        run(refusing.describe([IMAGE], 'wardrobe'))


def test_media_validation_and_no_untrusted_fetch():
    with pytest.raises(ValueError):
        run(load_image('http://127.0.0.1/private'))
    with pytest.raises(ValueError):
        run(load_image('https://evil.test/photo.png'))
    with pytest.raises(ValueError):
        validate_image('data:image/png;base64,bm90IGFuIGltYWdl')
    assert validate_image(IMAGE) == IMAGE


def test_photo_and_feed_api_auth_scope(tmp_path, monkeypatch):
    monkeypatch.setenv('HEM_DEV_TOKEN', 'dev-token')
    path = tmp_path / 'hem.db'
    engine = Assistant(Store(path), ai=FakeAI())
    headers = {'Authorization': 'Bearer dev-token'}
    with TestClient(create_app(path, assistant=engine)) as client:
        assert client.get('/dev/wardrobe/a').status_code == 403
        reply = client.post('/dev/chat', headers=headers, json={'user_id': 'a', 'images': [IMAGE]}).json()['reply']
        draft = re.search(r'Photo ([a-f0-9]{10})', reply)[1]
        client.post('/dev/chat', headers=headers, json={'user_id': 'a', 'text': 'confirm photo ' + draft})
        snapshot = client.get('/dev/wardrobe/a', headers=headers).json()
        asset_id = snapshot['details'][0]['asset_id']
        assert client.get(f'/dev/photos/a/{asset_id}', headers=headers).status_code == 200
        assert client.get(f'/dev/photos/b/{asset_id}', headers=headers).status_code == 404
        assert client.post('/dev/sources/import', headers=headers, json={'user_id': 'a', 'source_url': 'https://example.test/feed', 'xml': '<broken'}).status_code == 422


def test_weather_wire_format_and_missing_values():
    def handle(request):
        assert request.url.params['timezone'] == 'auto'
        assert request.url.params['start_date'] == '2026-09-20'
        return httpx.Response(200, json={'timezone': 'America/Toronto', 'daily': {
            'time': ['2026-09-20'], 'temperature_2m_min': [5], 'temperature_2m_max': [12],
            'apparent_temperature_min': [2], 'precipitation_probability_max': [80]}})
    weather = Weather(httpx.MockTransport(handle))
    assert run(weather.forecast(43.6, -79.4, '2026-09-20'))['rain_chance'] == 80
    with pytest.raises(ValueError):
        run(weather.forecast(float('nan'), 1))


def test_feed_fetch_does_not_follow_redirect_or_private_host():
    with pytest.raises(ValueError):
        run(fetch_feed('https://127.0.0.1/feed'))
    with pytest.raises(ValueError):
        run(fetch_feed('https://newsletter.substack.com/feed', httpx.MockTransport(lambda r:
            httpx.Response(302, headers={'location': 'http://127.0.0.1/private'}))))


def test_webhook_ack_precedes_ai_and_replay_does_not_repeat_work(tmp_path, monkeypatch):
    import time
    from test_hem import signed
    monkeypatch.setenv('LINQ_WEBHOOK_SECRET', 'whsec_' + base64.b64encode(b'test-secret').decode())
    monkeypatch.setenv('HEM_SEND_MESSAGES', 'false')
    class SlowAI(FakeAI):
        async def advise(self, context):
            await asyncio.sleep(0.3)
            return await super().advise(context)
    path = tmp_path / 'hem.db'
    engine = Assistant(Store(path), ai=SlowAI())
    payload = {'event_id': 'slow-event', 'event_type': 'message.received', 'data': {
        'id': 'slow-message', 'direction': 'inbound', 'chat': {'id': 'chat', 'is_group': False},
        'sender_handle': {'handle': '+15555550000', 'is_me': False},
        'parts': [{'type': 'text', 'value': 'How do colors work together?'}]}}
    app = create_app(path, assistant=engine)
    with TestClient(app) as client:
        body, headers = signed(payload)
        response = client.post('/webhooks/linq', content=body, headers=headers)
        assert response.status_code == 202 and response.json()['status'] == 'queued'
        with app.state.store.connect() as db:
            assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 0
        for _ in range(100):
            with app.state.store.connect() as db:
                finished = db.execute('SELECT count(*) FROM receipts').fetchone()[0]
            if finished:
                break
            time.sleep(0.02)
        assert finished == 1
        assert client.post('/webhooks/linq', content=body, headers=headers).json()['status'] == 'duplicate'
    with app.state.store.connect() as db:
        receipt = dict(db.execute('SELECT * FROM receipts').fetchone())
    restarted = Assistant(Store(path), ai=FakeAI())
    assert run(restarted.reply(receipt['user_id'], 'different text', request_id='slow-event')) == receipt['reply']
    with restarted.store.connect() as db:
        assert db.execute('SELECT count(*) FROM conversations').fetchone()[0] == 2


def test_inspiration_photo_matches_owned_clothes_without_importing(tmp_path):
    store = Store(tmp_path / 'hem.db')
    ai = FakeAI()
    engine = Assistant(store, ai=ai)
    for item in ('top: navy sweater', 'bottom: blue trousers', 'shoes: white sneakers'):
        run(engine.reply('a', 'add ' + item))
    ids = [g['id'] for g in store.snapshot('a')['wardrobe']]
    ai.advice = Advice(answer='Use your navy sweater and trousers; your sneakers make it more casual.', item_ids=ids, source_ids=[])
    reply = run(engine.reply('a', "Match this look from someone's outfit", [IMAGE]))
    assert 'Recreating the reference look' in reply
    assert ai.context['inspiration_garments'][0]['description'] == 'navy sweater'
    assert [g['id'] for g in store.snapshot('a')['wardrobe']] == ids
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM photo_drafts').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM photo_assets').fetchone()[0] == 0
    assert not store.snapshot('a')['wears']


def test_existing_draft_can_be_styled_without_confirmation(tmp_path):
    store = Store(tmp_path / 'hem.db')
    ai = FakeAI()
    engine = Assistant(store, ai=ai)
    reply = run(engine.reply('a', '', [IMAGE]))
    draft = re.search(r'Photo ([a-f0-9]{10})', reply)[1]
    ai.advice = Advice(answer='Add some owned clothes first so I can find a match.', item_ids=[], source_ids=[])
    run(engine.reply('a', f'style photo {draft}'))
    assert ai.context['inspiration_garments']
    assert not store.snapshot('a')['wardrobe']
    assert 'not available' in run(engine.reply('b', f'style photo {draft}'))
