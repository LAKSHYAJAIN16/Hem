import argparse
from hem.store import Store
from hem.stylist import chat


def main():
    parser = argparse.ArgumentParser(description='Local Hem conversation. No real messages are sent.')
    parser.add_argument('--database', default='data/hem.sqlite3')
    parser.add_argument('--user', default='local-demo')
    args = parser.parse_args()
    store = Store(args.database)
    print('Hem · local prototype. Type help or exit. No live iMessages are sent.')
    while True:
        try:
            text = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {'exit', 'quit'}:
            break
        if text:
            print('Hem:', chat(store, 'dev:' + args.user, text))


if __name__ == '__main__':
    main()
