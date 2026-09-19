# Hem

Your wardrobe. Your taste. Your next outfit.

Hem is an iMessage-first personal stylist: text what you own, get an outfit, and let your confirmed wear history and preferences inform the next suggestion.

## Working starter

- Persistent, per-user wardrobe and preference memory in SQLite.
- Outfit combinations from available clothes, with penalties for recently worn pieces.
- Explicit wear confirmation, history, and laundry availability.
- Local text simulator and FastAPI API.
- Linq V3 webhook signature verification, event/message deduplication, and a durable reply outbox.

This is a deterministic prototype, not a connected AI stylist. Photos, free-form advice, weather, live fashion databases, and VR are not implemented yet. Qdrant indexing/query and RSS/Atom parsing adapters exist and have mocked tests; they are not yet connected to the chat flow or a live embedding provider. No demo wardrobe is silently populated. Preferences currently match words in garment descriptions; occasion requests are stored but do not affect ranking. Wear dates use the server's local date.

## Run locally (PowerShell)

```powershell
cd C:\Users\laksh\Desktop\Projects\Hem
python -m hem.cli
```

The CLI needs only Python 3.11+ and sends no messages. Try:

```text
add top: navy cotton sweater
add top: cream linen shirt
add bottom: blue jeans
add shoes: white sneakers
I like navy
What should I wear today?
wore it
What should I wear today?
history
```

For the HTTP server:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
.venv\Scripts\python.exe -m uvicorn hem.app:create_app --factory --host 127.0.0.1 --port 8010 --workers 1
```

API docs: http://127.0.0.1:8010/docs. Set a random `HEM_DEV_TOKEN` in `.env` to use `/dev/chat` with a matching Bearer token. Local CLI users are isolated by `--user`; this is a development simulator, not user authentication.

Tests: `.venv\Scripts\python.exe -m pytest`.

## Linq integration

Configure a Linq account/number and a public HTTPS deployment. Subscribe `/webhooks/linq` to `message.received` using webhook version `2026-02-03`, and set `LINQ_WEBHOOK_SECRET`. See the official [webhook guide](https://docs.linqapp.com/channel/imessage/guides/webhooks/) and [event schemas](https://docs.linqapp.com/channel/imessage/guides/webhooks/events/).

Sending defaults to disabled. Signed incoming messages can update memory and save replies as `dry_run`; these are never sent later. To enable real replies after account setup, set `LINQ_API_KEY` and `HEM_SEND_MESSAGES=true`. No live connection has been tested. Run one server worker with this initial SQLite outbox implementation. Ambiguous send failures become `needs_review` rather than retrying and potentially duplicating a message. Review those records manually; no delivery-management UI exists yet.

Only direct inbound messages are handled. The sender handle maps to a hashed account ID; hashes are not anonymization. Database records contain private clothing/preferences/messages and require ordinary storage protection. Before public launch add account deletion/export, rate limits, operational monitoring, and a retention policy.

## Next build milestones

1. Connect Linq and verify one complete incoming-message/reply cycle.
2. Add image understanding with user confirmation before saving extracted clothing attributes.
3. Connect a conversational model to typed wardrobe tools, preserving explicit wear confirmation.
4. Add Qdrant for garment/style embeddings and permission-scoped retrieval. Keep exact wear dates and inventory in SQLite; use vectors for similarity, not factual history.
5. Ingest selected fashion catalogs and public/authorized newsletter feeds with source URLs and dates. Ground advice in retrieved material and clothes the user owns.
6. Optionally show suggested outfits in a Quest wardrobe room. Messaging remains the complete core experience.

## Retrieval adapters

`hem.retrieval.VectorIndex` supports creating a cosine collection, indexing documents, and queries scoped to one owner. Supply vectors from the same embedding model with the configured dimensions. IDs include the owner scope. These are internal service methods, not public endpoints: the caller must supply the authenticated owner, never a client-selected identity. See [Qdrant query API](https://api.qdrant.tech/api-reference/search/query-points).

`hem.sources.parse_feed(xml, source_url)` extracts RSS/Atom titles, summaries, dates, and source links from supplied feed contents, including newsletter feeds. It performs no network fetches and does not bypass paid subscriptions. Render extracted text as text, not HTML. Source content is untrusted reference material, never assistant instructions.

No vector service, embedding model, or newsletter subscription is installed. The next integration step is a configured embedding provider plus a source ingestion job, followed by wiring retrieved evidence into conversational advice.
