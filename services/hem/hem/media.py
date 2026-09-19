"""Bounded image inputs. Remote fetches only use explicitly trusted media hosts."""
import base64
import os
from urllib.parse import urlsplit

import httpx

MAX_IMAGE = 3_000_000


def validate_image(value):
    try:
        prefix, encoded = value.split(',', 1)
        mime = prefix.removeprefix('data:').removesuffix(';base64')
        if prefix != f'data:{mime};base64' or mime not in {'image/jpeg', 'image/png', 'image/webp'}:
            raise ValueError()
        if len(encoded) > 4 * ((MAX_IMAGE + 2) // 3):
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        valid = ((mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff')) or
                 (mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or
                 (mime == 'image/webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'))
        if not valid or len(raw) > MAX_IMAGE:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Use a JPEG, PNG or WebP image up to 3 MB.') from exc


async def load_image(value, transport=None):
    if value.startswith('data:'):
        return validate_image(value)
    parsed = urlsplit(value)
    hosts = {h.strip().lower() for h in os.getenv('HEM_MEDIA_HOSTS', 'cdn.linqapp.com').split(',') if h.strip()}
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('This image host is not configured. Upload image data directly or configure its trusted CDN host.')
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as client:
        async with client.stream('GET', value) as response:
            if response.is_redirect:
                raise ValueError('Image redirects are not supported.')
            response.raise_for_status()
            mime = response.headers.get('content-type', '').split(';')[0].lower()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_IMAGE:
                    raise ValueError('Image exceeds 3 MB.')
    return validate_image(f'data:{mime};base64,' + base64.b64encode(raw).decode())
