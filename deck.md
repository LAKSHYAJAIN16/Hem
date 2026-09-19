# Hem
## Slide 1 — Your wardrobe. Your taste. Your next outfit.

A personal stylist in your messages that remembers what you own, what you like, and what you actually wore.

Speaker note: Lead with the morning decision, then show the conversation. Do not open with the technology stack.

---

## Slide 2 — A full closet, the same daily question

“What should I wear?” still means remembering clean clothes, recent outfits, and what goes together. Inspiration feeds rarely know what is already in your closet.

Hem's starting point: help someone use the clothes they own.

---

## Slide 3 — Text your stylist

Target experience:

1. Send a garment photo or description.
2. Ask for an outfit for your day.
3. Explain a preference: “I like navy; skip orange.”
4. Confirm “wore it” so the next recommendation accounts for it.

Today: descriptions, preferences, suggestions, and wear confirmation work in the local simulator. Photo recognition and open-ended styling are planned. Live iMessage needs Linq credentials and deployment.

---

## Slide 4 — Memory changes the next answer

An outfit suggestion is not proof that you wore it. Hem records history only after confirmation, then penalizes recent repeats and excludes laundry items.

This gives the demo a visible cause and effect: wear the first suggestion, request another, and see the available alternative rise.

---

## Slide 5 — Demo: one minute, no hidden setup

Add a navy sweater, cream shirt, jeans, and sneakers. Say “I like navy,” ask for an outfit, then say “wore it.” Ask again and show the changed top. Show history and the saved preference.

Use the local CLI until live Linq is verified. Label any proposed photo or newsletter sequence as a storyboard, not a live demo.

---

## Slide 6 — Built around the conversation

- Linq: signed incoming messages and an outgoing reply adapter.
- Python/FastAPI: conversation commands and outfit ranking.
- SQLite: inventory, preferences, confirmed wear history, and reply outbox.
- Qdrant adapter: owner-scoped vector indexing and queries, awaiting embeddings/service connection.
- RSS/Atom parser: source-attributed inspiration, awaiting ingestion and retrieval integration.

Current ranking is deterministic. AI-generated advice is a next integration, not a current claim.

---

## Slide 7 — Inspiration that knows your closet

Next: retrieve relevant garment/style references, cite their sources, and translate inspiration into combinations of owned clothes. Keep factual inventory and dates separate from semantic similarity.

Optional later extension: a Quest wardrobe room for comparing looks. The complete everyday flow should stay in messaging.

---

## Slide 8 — What we can prove today

Eight automated tests pass for persistence, user isolation, wear confirmation, rotation, laundry, webhook signatures/deduplication, access controls, vector query scoping, and feed parsing.

No live Linq, Qdrant, embedding, vision, or headset test has been completed. No user-growth, accuracy, or sustainability metrics are claimed.

---

## Slide 9 — Sponsor fit and next milestone

Primary target: Linq's messaging utility track. Proposed additional fits: vector retrieval, persistent AI memory, and multimodal understanding. Exact sponsor eligibility is pending the event's prize list.

Next milestone: a real text arriving through Linq, a grounded outfit response, and a second recommendation that reflects confirmed wear history.

Close: “A stylist that remembers your closet—and your last outfit.”

References and implementation attribution: [SOURCES.md](SOURCES.md). Build record: [CODEX_LOG.md](CODEX_LOG.md).
