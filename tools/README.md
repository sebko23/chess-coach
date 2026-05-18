# `tools/` — Developer tooling

**License**: Apache-2.0.

Phase-1 tools planned:

- `ci/check_forbidden_paths.py` — enforces the en-croissant edit allowlist (`docs/15_integration_surfaces/en-croissant.md` §7.1).
- `ci/check_file_headers.py` — enforces SPDX headers per the integration contract §7.2.
- `ci/check_tier_rules.py` — enforces the agent-tier dependency rule (`docs/06_multi_agent/multi-agent-workflow.md`).
- `gen/regen_schemas.py` — regenerates `specs/v1.0/schemas/*.schema.json` from `libs/protocol_types/`.
- `gen/regen_ts_client.py` — regenerates `apps/desktop/src/services/coach/client.ts` from the schemas.
