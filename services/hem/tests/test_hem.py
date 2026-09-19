import base64
import hashlib
import hmac
import json
import time
from datetime import date

from fastapi.testclient import TestClient

from hem.app import create_app
from hem.linq import verify
from hem.store import Store
from hem.stylist import chat


def test_memory_persistence_and_isolation(tmp_path):
    path = tmp_path / 'hem.db'
    store = Store(path)
    chat(store, 'alice', 'I like navy')
    chat(store, 'alice', 'add top: navy sweater')
    restored = Store(path)
    assert 'navy' in chat(restored, 'alice', 'preferences')
    assert not restored.snapshot('bob')['wardrobe']
    assert not restored.snapshot('bob')['preferences']
    chat(restored, 'alice', 'forget navy')
    assert not restored.snapshot('alice')['preferences']


def test_wear_confirmation_rotation_and_laundry(tmp_path):
    store = Store(tmp_path / 'hem.db')
    for item in ['top: navy sweater', 'top: cream tee', 'bottom: blue jeans', 'shoes: white sneakers']:
        chat(store, 'a', 'add ' + item)
    first = chat(store, 'a', 'outfit', date(2026, 9, 19))
    assert 'navy sweater' in first
    assert not store.snapshot('a')['wears']
    chat(store, 'a', 'wore it', date(2026, 9, 19))
    chat(store, 'a', 'wore it', date(2026, 9, 19))
    assert len(store.snapshot('a')['wears']) == 1
    second = chat(store, 'a', 'outfit', date(2026, 9, 20))
    assert 'cream tee' in second
    shoe = next(i for i in store.snapshot('a')['wardrobe'] if i['category'] == 'shoes')
    chat(store, 'b', 'laundry ' + shoe['id'])
    assert store.snapshot('a')['wardrobe'][-1]['available'] == 1
    chat(store, 'a', 'laundry ' + shoe['id'])
    assert 'I need' in chat(store, 'a', 'outfit')


def signed(payload, key=b'test-secret'):
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    event = payload['event_id']
    digest = hmac.new(key, f'{event}.{stamp}.'.encode() + body, hashlib.sha256).digest()
    return body, {'webhook-id': event, 'webhook-timestamp': stamp,
                  'webhook-signature': 'v1,' + base64.b64encode(digest).decode(),
                  'content-type': 'application/json'}


def test_signature_tampering_and_expiry():
    body, headers = signed({'event_id': 'e1'})
    secret = 'whsec_' + base64.b64encode(b'test-secret').decode()
    assert verify(secret, body, headers)
    assert not verify(secret, body + b' ', headers)
    assert not verify(secret, body, headers, now=int(headers['webhook-timestamp']) + 301)


def test_webhook_idempotency_and_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv('LINQ_WEBHOOK_SECRET', 'whsec_' + base64.b64encode(b'test-secret').decode())
    monkeypatch.setenv('HEM_SEND_MESSAGES', 'false')
    app = create_app(tmp_path / 'hem.db')
    payload = {'event_id': 'e1', 'event_type': 'message.received', 'data': {
        'id': 'm1', 'direction': 'inbound', 'chat': {'id': 'c1', 'is_group': False},
        'sender_handle': {'handle': '+15555550123', 'is_me': False},
        'parts': [{'type': 'text', 'value': 'add top: navy sweater'}]}}
    with TestClient(app) as client:
        body, headers = signed(payload)
        assert client.post('/webhooks/linq', content=body, headers=headers).json()['status'] == 'queued'
        assert client.post('/webhooks/linq', content=body, headers=headers).json()['status'] == 'duplicate'
        payload['event_id'] = 'e2'
        body, headers = signed(payload)
        assert client.post('/webhooks/linq', content=body, headers=headers).json()['status'] == 'duplicate'
        payload['event_id'] = 'e3'
        payload['data']['chat']['is_group'] = True
        body, headers = signed(payload)
        assert client.post('/webhooks/linq', content=body, headers=headers).json()['status'] == 'ignored'
        for _ in range(100):
            with app.state.store.connect() as db:
                processed = db.execute('SELECT count(*) FROM events').fetchone()[0]
            if processed:
                break
            time.sleep(0.02)
    with app.state.store.connect() as db:
        assert db.execute('SELECT count(*) FROM garments').fetchone()[0] == 1
        assert db.execute('SELECT status FROM events').fetchone()[0] == 'dry_run'


def test_http_endpoints_fail_closed(tmp_path, monkeypatch):
    monkeypatch.delenv('LINQ_WEBHOOK_SECRET', raising=False)
    monkeypatch.setenv('HEM_DEV_TOKEN', 'local-token')
    with TestClient(create_app(tmp_path / 'hem.db')) as client:
        assert client.post('/webhooks/linq', json={}).status_code == 503
        message = {'user_id': 'alice', 'text': 'hello'}
        assert client.post('/dev/chat', json=message).status_code == 403
        assert client.post('/dev/chat', json=message, headers={'Authorization': 'Bearer local-token'}).status_code == 200
