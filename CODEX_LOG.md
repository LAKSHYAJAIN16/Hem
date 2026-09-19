# Codex work log — Hem

## 2026-09-19 — Initial implementation

Requested location: `C:\Users\laksh\Desktop\Projects\Hem`. The user selected the Hem name and an iMessage-first fashion companion, then requested sources/credits, a deck, and this log. API keys will be provided later.

### Work performed

- Created the new project directory independently of Ramsey.
- Added Python packaging, environment template, ignore rules, and setup documentation.
- Implemented persistent per-user wardrobe, likes/dislikes, outfit suggestions, explicit wear logging, history, and laundry availability.
- Added a local CLI and token-protected HTTP simulator.
- Added Linq V3 inbound parsing, timestamped HMAC verification, event/message deduplication, and an outbox. Sending defaults off; dry-run replies cannot be sent later by merely enabling delivery.
- Added a Qdrant HTTP adapter with owner-scoped vectors and queries, plus RSS/Atom parsing with source attribution. Neither is connected to live services or the stylist flow yet.
- Added eight automated tests, a slide-ready deck, and sources/credits inventory.

### Validation

Eight tests passed using the existing development test environment against temporary SQLite databases and fake HTTP transport. The first sandboxed test run could not access pytest's temporary directory; the permitted rerun succeeded. Two dependency deprecation warnings were emitted by the existing FastAPI/Starlette test client stack.

Live messaging, live vector retrieval, image understanding, and AI advice have not been validated. No outbound messages were sent. No credentials were copied from Ramsey.

### Decisions and limits

- Exact records use SQLite; vectors are reserved for similarity retrieval.
- Recommendations do not silently become wear history.
- The prototype uses deterministic text matching, not a hidden or simulated language model.
- The initial outbox supports a single server worker; uncertain sends require review.
- A sponsor/prize list was requested before naming additional eligible tracks.
- The deck distinguishes the implemented starter from the intended experience.

This is a factual development summary, not a verbatim conversation transcript or a record of private reasoning. Append dated entries as implementation and live validation proceed.

## 2026-09-19 — Independent environment and concise README

Created Hem's own .venv, installed its dependencies, and reran its tests: 8 passed, with two dependency deprecation warnings. Reworked README into the requested compact format and preserved full instructions in SETUP_NOTES.md. No live integrations or outgoing messages were used for validation.

The user requested the GitHub remote https://github.com/LAKSHYAJAIN16/Hem.git. Its branch listing was empty when checked. Local Git initialization and origin configuration are the next setup action; no publication is claimed by this entry.

## 2026-09-19 — Repository organization and local webhook tunnel

Organized the Python package and tests under `services/hem`, setup documentation
under `docs`, tunnel instructions under `infra`, and integration commands under
`scripts`, following the relevant structure of michaelmazilu/cut-once. Updated
package discovery and root environment-file resolution. Retained root README,
deck, sources, and this development log. The requested remote is configured as origin.

Started a Cloudflare quick tunnel and registered a Linq subscription. API and signing
secrets, registration response, downloaded client, and operational logs remain in
ignored local files.

Validation: all 8 service tests passed after relocating the package. Public health
check passed; a signed synthetic message.sent event was safely ignored and an
unsigned request returned 401. No actual incoming-message/reply cycle has been
tested and no outbound message was sent. The quick tunnel URL changes when the
tunnel is recreated and requires updating the Linq subscription.

## 2026-09-19 — Photo wardrobe, contextual styling and approval requests

Added structured wardrobe-photo recognition with correction and confirmation,
conversational styling constrained to available owned garments, dated weather,
occasion-aware fallback ranking, and per-user RSS/Atom inspiration retrieval.
Added automatic preparation of care requests from user-defined wear intervals,
shopping request drafts, and explicit approval/cancellation/completion commands.
External provider bookings and purchases are separate from request approval.

Incoming iMessages now enter a durable queue, with receipts to prevent repeated
mutations after restart. Added authenticated local wardrobe/photo endpoints,
source-import and live-check scripts, and a Unity/OpenXR companion design.
Public READMEs focus on usage and supported features; credentials and private
account diagnostics stay out of the repository.

Validation: 19 tests passed, covering multi-item photo confirmation, owner isolation,
model-output validation, weather ranking, citations, care counters, request approval,
webhook queue acknowledgement, replay receipts, and HTTP access controls. Live weather
and public webhook health/signature checks passed. The operator enabled reply delivery.

## 2026-09-19 — Recreate a reference outfit

Added inspiration-photo routing for captions such as 'match this look' and an explicit
API photo mode. Reference attributes guide owned-wardrobe selection without importing
the photographed garments. Existing unconfirmed photo drafts can also be used as
references with `style photo <ID>`. Added owner-isolation and no-import regressions;
the complete suite passes 21 tests.

## 2026-09-19 — Conversational wardrobe input

Added an OpenAI intent router for natural ownership statements, inferred garment
categories, photo corrections and confirmations, availability updates, preferences,
and location changes. Photo dialogue focus scopes short confirmations to the current
discussion. Natural wardrobe replies omit internal IDs and category syntax. Added
Toronto as the default weather location and retained explicit location override/opt-out.
The suite passes 26 tests including natural descriptions, corrections, stale-confirmation
protection, router context, and weather defaults.
