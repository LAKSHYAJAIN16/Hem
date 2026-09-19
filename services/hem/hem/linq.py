"""Linq V3 transport and Standard Webhooks verification. No account setup side effects."""
import base64
import hashlib
import hmac
import time
from urllib.parse import quote

import httpx


def verify(secret, body, headers, now=None):
    try:
        stamp = headers['webhook-timestamp']
        if abs((time.time() if now is None else now) - int(stamp)) > 300:
            return False
        key = base64.b64decode(secret.removeprefix('whsec_'), validate=True)
        if not key:
            return False
        signed = f"{headers['webhook-id']}.{stamp}.".encode() + body
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(expected, sig[3:]) for sig in headers['webhook-signature'].split() if sig.startswith('v1,'))
    except (KeyError, ValueError, TypeError):
        return False


def inbound(payload):
    if payload.get('event_type') != 'message.received':
        return None
    data = payload.get('data') or {}
    chat = data.get('chat') or {}
    sender = data.get('sender_handle') or {}
    if data.get('direction') != 'inbound' or chat.get('is_group') or sender.get('is_me'):
        return None
    handle = sender.get('handle')
    if not isinstance(handle, str) or not handle or not chat.get('id') or not data.get('id'):
        raise ValueError('Missing sender, chat or message ID. Expected the 2026-02-03 webhook format.')
    text = '\n'.join(p.get('value', '') for p in data.get('parts', []) if p.get('type') == 'text')
    has_media = any(p.get('type') == 'media' for p in data.get('parts', []))
    return {'user_id': hashlib.sha256(handle.strip().lower().encode()).hexdigest(),
            'chat_id': chat['id'], 'message_id': data['id'], 'text': text[:4000], 'has_media': has_media}


async def send_reply(api_key, chat_id, reply):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f'https://api.linqapp.com/api/partner/v3/chats/{quote(chat_id, safe="")}/messages',
            headers={'Authorization': f'Bearer {api_key}'},
            json={'message': {'parts': [{'type': 'text', 'value': reply}]}},
        )
        response.raise_for_status()
