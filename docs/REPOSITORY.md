# Repository layout

Following the service-oriented structure of https://github.com/michaelmazilu/cut-once:

- `services/hem/hem/`: Python API, CLI, wardrobe engine, and integrations.
- `services/hem/tests/`: service tests.
- `scripts/`: development and integration setup commands.
- `infra/`: tunnel and deployment instructions.
- `docs/`: setup and architecture documentation.
- `data/`: ignored local databases, tools, logs, and integration state.
- Root: package configuration, README, deck, sources, and development log.

Add `apps/` when a frontend exists and `packages/` when shared code is extracted.
Keep secrets and local runtime artifacts out of commits. Commit and push completed,
validated increments to the configured Hem remote.
