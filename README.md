# Hem

A personal stylist in your messages. Remembers your wardrobe, your taste, and what you actually wore.

[Deck](deck.md) · [Build and setup](docs/SETUP_NOTES.md) · [Codex log](CODEX_LOG.md)

[Repository layout](docs/REPOSITORY.md) · [Local tunnel](infra/README.md)

## Two ideas hold it together

**Your own clothes come first.** Suggestions use your available wardrobe. Preferences influence the choice; clothes in the laundry stay out. Fashion sources will add inspiration grounded in what you own.

**A suggestion is not a memory.** Hem logs an outfit only when you say “wore it.” Confirmed history informs the next recommendation. SQLite keeps the facts; vector retrieval is for similarity and inspiration.

## Run it

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env             # configure integrations when ready
.venv\Scripts\python.exe -m hem.cli    # local conversation; no keys needed
```

Try `add top: navy sweater`, `add bottom: blue jeans`, `add shoes: white sneakers`, then `What should I wear today?` and `wore it`.

```powershell
.venv\Scripts\python.exe -m uvicorn hem.app:create_app --factory --host 127.0.0.1 --port 8010 --workers 1
.venv\Scripts\python.exe -m pytest
```

Useful: [API docs](http://127.0.0.1:8010/docs), `wardrobe`, `preferences`, `history`, `laundry <item ID>`, `clean <item ID>`. The HTTP simulator requires `HEM_DEV_TOKEN`. Linq setup and retrieval details: [docs/SETUP_NOTES.md](docs/SETUP_NOTES.md).

## Honest labels

**Working locally:** wardrobe storage, preference memory, deterministic outfit ranking, confirmed wear history, repeat penalties, laundry availability, CLI and HTTP simulator. Eight automated tests pass.

**Implemented adapters, not live integrations:** signed Linq webhooks and reply outbox, owner-scoped Qdrant requests, RSS/Atom parsing. No API keys, embedding provider, live vector service, or newsletter ingestion job is connected. Outbound messaging defaults off.

**Planned:** garment photo understanding, conversational AI fashion advice, occasion/weather-aware styling, source-grounded recommendations, and an optional Quest wardrobe room.

Sources and credits: [SOURCES.md](SOURCES.md). Development record: [CODEX_LOG.md](CODEX_LOG.md).
