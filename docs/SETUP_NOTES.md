# Build and setup

Run commands from the repository root. Install with
`.venv/Scripts/python.exe -m pip install -e ".[test]"` and copy `.env.example` to
`.env` once. Keep personal configuration and runtime data in ignored local files.

## Configuration

| Setting | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API project credential |
| `OPENAI_MODEL` | Image-capable Responses API model supporting structured outputs; default template uses `gpt-4.1-mini` |
| `LINQ_API_KEY` | Linq account API credential |
| `LINQ_WEBHOOK_SECRET` | Signing secret returned when registering the webhook |
| `HEM_SEND_MESSAGES` | Set to `true` to send replies to incoming iMessages |
| `HEM_DEV_TOKEN` | Random bearer token for local API clients |
| `HEM_MEDIA_HOSTS` | Exact trusted photo CDN hosts; default `cdn.linqapp.com` |
| `HEM_SOURCE_HOSTS` | Additional exact trusted RSS publisher hosts |
| `HEM_DEFAULT_CITY`, `HEM_DEFAULT_LATITUDE`, `HEM_DEFAULT_LONGITUDE` | Default weather context; Toronto at 43.65, -79.38 |
| `HEM_DATABASE` | SQLite path; default `data/hem.sqlite3` |

Start the API with one worker:

```powershell
.venv/Scripts/python.exe -m uvicorn hem.app:create_app --factory --host 127.0.0.1 --port 8010 --workers 1
```

Restart after changing environment configuration. The API is at
http://127.0.0.1:8010/docs. Use [the tunnel guide](../infra/README.md) to connect
Linq. Signed incoming events enter a durable queue; conversation receipts make
replay after a process restart idempotent. Delivery state is separate from wardrobe
and wear history. Development users use the `dev:` namespace; iMessage users are
scoped to a hash of their sender handle.

## Wardrobe photos

Send a wardrobe photo over iMessage, or supply `images` in `/dev/chat` as base64
JPEG, PNG, or WebP data URLs. Up to two images, each at most 3 MB, are accepted per
request. Include different sections of a crowded wardrobe across several messages.
Hem identifies up to twelve visible garments per batch and asks you to review them.
OpenAI interprets ordinary descriptions and corrections and infers garment categories.
Users do not need to provide category labels or record IDs.

```text
I own a navy sweater and blue jeans
Actually the first one is a charcoal jacket
Yes, add those
Only the navy sweater
No thanks
Show me my clothes
My blue jeans are in the wash
```

Short confirmations apply to the photo currently under discussion. An unrelated
conversation clears that focus so a later 'yes' does not save an old draft. Explicit
ID-based commands remain available for development tools and older clients.

Selection confirms the chosen items and closes that draft. Photo-derived material,
warmth and formality are tentative attributes, and a text correction clears those
inferences. The original photo is stored locally for review; single-photo drafts
can link it to confirmed garments. This is a reference image, not a garment crop
or a 3D model. API photo access requires the development bearer token.

For someone else's outfit, caption the photo **match this look** or set API
`photo_mode` to `inspiration`. Hem extracts visible style attributes and selects
the closest combination from your available wardrobe, explaining substitutions.
Reference garments are never added to your wardrobe. If a photo was already
analyzed as a wardrobe draft, saying 'those are not mine, use them as inspiration' reuses it without
confirming ownership. The API also supports `photo_mode=wardrobe` to explicitly
import a photo of your own clothes.

## Styling and weather

Toronto is used by default. Say 'I live in <city>' to change the weather location.
Development clients can also provide explicit coordinates with
`location 43.65,-79.38 Toronto`. Remove weather context with `location clear`.
Open-Meteo supplies dated Celsius forecasts. Use today, tomorrow, an ISO date in
your message, or the API's `on_date` field. The API also accepts an explicit
`occasion`. Advice includes the forecast date and source when weather is used.

The AI receives your available wardrobe, saved attributes and preferences, recent
conversation, confirmed wears, and relevant source excerpts. Selected garment IDs
are checked against your current available wardrobe before an outfit is saved.
Use `wore it` to record a wear; asking for advice never logs one.

## Fashion sources

Import a public Substack feed with `source https://publication.substack.com/feed`.
Additional publishers can be configured through `HEM_SOURCE_HOSTS`. Redirects
are rejected; use the final feed URL. To import an authorized local RSS/Atom export:

```powershell
.venv/Scripts/python.exe scripts/import_inspiration.py data/inspiration.xml --source-url https://publisher.example/feed --user local-demo
```

Use `--sender <incoming E.164 handle>` instead of `--user` for an iMessage wardrobe.
The authenticated `/dev/sources/import` endpoint accepts `user_id`, `source_url`,
and `xml`. Imports preserve links and publication dates, and repeated imports
update the same entries. Per-user lexical retrieval selects relevant excerpts;
validated source IDs become citations in the reply. General advice is labeled
separately when no imported source is cited. Import only public or authorized
content. Publisher text is treated as data, never as executable instructions.

## Care and shopping requests

```text
care <item ID>: laundry every 3 wears
care <item ID>: dryclean every 5 wears
auto laundry
auto drycleaner
auto order: waterproof boots, size 9, budget CAD 150
requests
approve request <ID>
cancel request <ID>
complete request <ID>
```

Care rules come from the user and the garment care label. Confirmed wears increment
their counters and prepare due requests. Approval marks a request ready to arrange;
it does not book, send a provider message, charge a payment method, or purchase.
Confirm the provider, quote, address, and time before arranging a service. Mark a
cleaning request complete after the real-world work is done to reset its counters
and return garments to availability. Order requests capture the brief and the
product, price, size, shipping and payment details that need confirmation.

## Validation

`.venv/Scripts/python.exe -m pytest` runs isolated tests with mocked providers.
`.venv/Scripts/python.exe scripts/live_check.py --photo data/wardrobe.jpg` runs
opt-in live weather and paid AI checks against temporary records, with no messaging.
`.venv/Scripts/python.exe scripts/check_tunnel.py` checks public health and signed
webhook acceptance using an ignored event.

Local `/dev/*` endpoints use an operator token and caller-selected development
identities. A deployed multi-user client needs account authentication and a
server-derived owner identity before accessing private wardrobes.
