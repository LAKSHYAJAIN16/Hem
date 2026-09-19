import argparse
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from hem.assistant import Assistant
from hem.store import Store


def main():
    load_dotenv(Path(__file__).resolve().parents[3] / '.env')
    parser = argparse.ArgumentParser(description='Local Hem conversation. No real messages are sent.')
    parser.add_argument('--database', default='data/hem.sqlite3')
    parser.add_argument('--user', default='local-demo')
    args = parser.parse_args()
    store = Store(args.database)
    engine = Assistant(store)
    print('Hem · local prototype. Type help or exit. No live iMessages are sent.')
    while True:
        try:
            text = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {'exit', 'quit'}:
            break
        if text:
            print('Hem:', asyncio.run(engine.reply('dev:' + args.user, text)))


if __name__ == '__main__':
    main()
