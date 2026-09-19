"""Check public health and signature verification without creating messages."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / '.env')
subscription = json.loads((root / 'data/linq-subscription.json').read_text())
target = subscription['target_url']
event_id = str(uuid.uuid4())
stamp = str(int(time.time()))
body = json.dumps({'event_id': event_id, 'event_type': 'message.sent', 'data': {}}).encode()
key = base64.b64decode(config['LINQ_WEBHOOK_SECRET'].removeprefix('whsec_'))
signature = base64.b64encode(hmac.new(key, f'{event_id}.{stamp}.'.encode() + body, hashlib.sha256).digest()).decode()
with httpx.Client(timeout=30) as client:
    health = client.get(target.split('/webhooks/')[0] + '/health')
    health.raise_for_status()
    valid = client.post(target, content=body, headers={'webhook-id': event_id,
                        'webhook-timestamp': stamp, 'webhook-signature': 'v1,' + signature})
    assert valid.status_code == 200 and valid.json() == {'status': 'ignored'}, valid.status_code
    invalid = client.post(target, content=body)
    assert invalid.status_code == 401, invalid.status_code
print('Public health OK; signed non-message event accepted; unsigned event rejected.')
