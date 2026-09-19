"""Register the active local tunnel with Linq; keep returned secrets out of stdout."""
import json
import re
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / '.env')
    urls = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', (ROOT / 'data/tunnel.log').read_text())
    if not urls:
        raise SystemExit('Tunnel URL not found in data/tunnel.log')
    target = urls[-1] + '/webhooks/linq?version=2026-02-03'
    record = ROOT / 'data/linq-subscription.json'
    if record.exists():
        raise SystemExit('Subscription record already exists; inspect it before creating another.')
    response = httpx.post(
        'https://api.linqapp.com/api/partner/v3/webhook-subscriptions',
        headers={'Authorization': 'Bearer ' + config['LINQ_API_KEY']},
        json={'target_url': target,
              'subscribed_events': ['message.received', 'message.sent', 'message.delivered', 'message.read'],
              'phone_numbers': [sys.argv[1]]}, timeout=30,
    )
    if response.status_code >= 400:
        print('Linq returned', response.status_code, response.text)
        raise SystemExit(1)
    subscription = response.json()
    record.write_text(json.dumps(subscription, indent=2))
    set_key(ROOT / '.env', 'LINQ_WEBHOOK_SECRET', subscription['signing_secret'])
    print('Registered webhook:', target)
    print('Signing secret saved in .env; response backed up in ignored data folder.')


if __name__ == '__main__':
    main()
