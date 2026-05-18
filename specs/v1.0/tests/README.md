# Conformance Test Vectors — Protocol v1.0

## What this is

A portable conformance suite that verifies whether a given backend or GUI implementation conforms to protocol v1.0. Spec §14 ('Reference Test Vectors') lists the test categories.

License: **MIT** (test code is broadly reusable; we want third parties to be able to ship their own conformance results).

## Layout

| File / Directory | Purpose |
|---|---|
| `runner.py` | Pytest-based runner. Targets a backend by base URL. |
| `cases/` | Test cases as JSON: `{request, expected_response_shape, assertions}`. |
| `fixtures/` | Reference PGNs, FENs, and expected analysis snapshots. |
| `vectors.json` | Index of cases; mirrors spec §14 categories. |

## Running

```bash
python -m chess_coach.testkit.run_conformance \
  --target backend \
  --base-url http://127.0.0.1:8765
```

(Available once the test runner is implemented in Phase 1.)

## Third-party use

A third party building a CHESS COACH-conforming backend can run these tests unmodified against their implementation and publish the result. We will link community conformance reports from `specs/README.md` once they exist.
