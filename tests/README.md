# `tests/` — Test suites

**License**: Apache-2.0.

| Subdirectory | Scope |
|---|---|
| `unit/` | Per-package unit tests. Fast (<5s suite). |
| `integration/` | Cross-package tests inside the backend process. |
| `e2e/` | Full GUI ↔ Backend round-trip tests (Playwright + headless Tauri). |
| `perf/` | Performance / event-loop-stall budgets (`docs/09_performance/performance-strategy.md`). |
| `golden/` | Golden-output regression tests (e.g. "this PGN should produce this analysis"). |

Conformance tests live separately at `specs/v1.0/tests/` (MIT licensed; intended for third-party reuse).
