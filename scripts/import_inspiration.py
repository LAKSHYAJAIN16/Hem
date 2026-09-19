"""Import a public/authorized RSS or Atom export for a CLI or iMessage owner."""
import argparse
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from hem.sources import import_feed
from hem.store import Store

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=Path)
    parser.add_argument('--source-url', required=True)
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument('--user', help='Local CLI/API user name')
    owner.add_argument('--sender', help='Exact incoming Linq sender handle, e.g. an E.164 phone number')
    args = parser.parse_args()
    user = 'dev:' + args.user if args.user else hashlib.sha256(args.sender.strip().lower().encode()).hexdigest()
    store = Store(os.getenv('HEM_DATABASE', str(ROOT / 'data/hem.sqlite3')))
    count = import_feed(store, user, args.file.read_bytes(), args.source_url)
    print(f'Imported {count} source documents with original links and publication dates.')


if __name__ == '__main__':
    main()
