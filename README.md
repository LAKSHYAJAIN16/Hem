# Hem

A personal stylist in your messages. Start with a photo of your wardrobe, confirm
the clothes Hem finds, and ask what to wear.

[Deck](deck.md) · [Setup](docs/SETUP_NOTES.md) · [Repository layout](docs/REPOSITORY.md) · [VR integration](docs/VR.md)

Hem combines your available clothes, preferences, confirmed outfit history,
occasion, weather, and linked fashion inspiration. Photo imports are reviewed
before becoming wardrobe items. Laundry, dry-cleaning, and shopping requests are
prepared for your approval.

## Run

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
# Configure the integrations in .env using the setup guide.
.venv/Scripts/python.exe -m uvicorn hem.app:create_app --factory --host 127.0.0.1 --port 8010 --workers 1
```

[Local API](http://127.0.0.1:8010/docs) · [iMessage tunnel](infra/README.md)

## Try it

- Send a wardrobe photo, then `confirm photo <ID>`.
- Send an outfit you like with “match this look” to recreate it from your own clothes.
- Set `location Toronto` and ask, “What should I wear to the office tomorrow?”
- Say `wore it` after wearing an outfit.
- Add inspiration with `source https://publication.substack.com/feed`.
- Set `care <item ID>: laundry every 3 wears` for automatic request preparation.
- Try `auto order: waterproof boots, size 9, budget CAD 150`, then review `requests`.

For a terminal conversation: `.venv/Scripts/python.exe -m hem.cli`.
Run the tests with `.venv/Scripts/python.exe -m pytest`.

[Sources and credits](SOURCES.md) · [Development log](CODEX_LOG.md)
