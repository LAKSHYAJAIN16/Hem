# Sources and credits

## Project

Hem is a hackathon prototype conceived by Laksh through the project conversation, with implementation assistance from OpenAI Codex. This repository contains newly written application code. No code, credentials, or user records were copied from the earlier Ramsey application.

## Documentation consulted

Accessed September 19, 2026:

- [Linq V3 quickstart](https://docs.linqapp.com/channel/imessage/getting-started/quickstart/) — messaging endpoint and request format.
- [Linq webhook guide](https://docs.linqapp.com/channel/imessage/guides/webhooks/) — signed request verification and delivery handling.
- [Linq webhook events](https://docs.linqapp.com/channel/imessage/guides/webhooks/events/) — inbound event envelope and message fields.
- [Qdrant query API](https://api.qdrant.tech/api-reference/search/query-points) — vector query requests and payload filters.
- [Qdrant upsert API](https://api.qdrant.tech/api-reference/points/upsert-points) — document/vector indexing requests.
- [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision) — wardrobe photo interpretation.
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) — validated garment and advice schemas.
- [Open-Meteo forecast API](https://open-meteo.com/en/docs) — dated weather context and attribution.
- [Unity XR Interaction Toolkit](https://docs.unity3d.com/Packages/com.unity.xr.interaction.toolkit@3.0/manual/index.html) — proposed VR client interaction design.

These sources informed integration code; they do not imply sponsorship, endorsement, or a verified live connection.

## Software dependencies

Direct dependencies declared in `pyproject.toml`:

| Package | Purpose | Upstream |
| --- | --- | --- |
| FastAPI | HTTP service | https://github.com/fastapi/fastapi |
| Uvicorn | ASGI server | https://github.com/encode/uvicorn |
| HTTPX | HTTP transport | https://github.com/encode/httpx |
| python-dotenv | Local configuration | https://github.com/theskumar/python-dotenv |
| pytest | Development tests | https://github.com/pytest-dev/pytest |
| setuptools | Package build tooling | https://github.com/pypa/setuptools |

Python's standard library supplies SQLite access, hashing, XML parsing, and the CLI. Transitive dependencies and their license notices remain governed by their upstream distributions. This document is an attribution inventory, not a replacement for those notices or a completed license audit.

## Fashion data and creative assets

No external fashion catalog, Substack article, newsletter corpus, garment photograph, font, or other creative asset is bundled. Test garments, feed snippets, phone numbers, and domains are synthetic fixtures, not sourced fashion advice. No AI-generated fashion images are included.

When adding a source, record its publisher, original URL, access date, license or permission basis, and exactly what is stored. Keep source links and publication dates with retrieved passages. Do not present another publisher's advice as Hem's original reporting or assume that public access permits redistribution.

| Future source | Publisher / creator | Original URL | Access date | Permission / license | Stored material |
| --- | --- | --- | --- | --- | --- |
| None connected yet | — | — | — | — | — |

## Service status

The service integrates Linq messaging, OpenAI Responses for structured photo recognition
and advice, Open-Meteo forecasts, and per-user RSS/Atom retrieval with source citations.
The environment template selects `gpt-4.1-mini`; deployments can configure a compatible
model. OpenAI requests use `store=false` and include only the relevant wardrobe,
conversation, photo and source context. API credentials and account diagnostics remain
in local configuration. Qdrant remains an optional adapter. The VR client design is
documented in `docs/VR.md`.
