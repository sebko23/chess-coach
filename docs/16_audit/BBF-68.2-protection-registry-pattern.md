# ProtectionRegistry pattern (per-process state primitives for external services)

Codifies the BBF-68.2 shape (2026-07-18). Use whenever a BBF wraps an
external service (LLM router, search index, third-party OCR, payment
processor, etc.) and needs per-backend rate limiting + circuit breaking
without external state.

## Why this pattern exists

External services that chess-coach calls have inconsistent SLAs:

- **chessvision.ai** (the OCR default): no API key, no SLA, throttles
  at ~70 KB/s sustained, occasional 503s.
- **OpenRouter** (the LLM router): has an API key + SLA, but quota
  exceeded returns 429 and we don't want a thundering herd to keep
  retrying.
- **Qdrant** (the local sidecar): usually up, but vector reindex
  jobs can spike CPU.
- **Future backends (Stripe, Sentry, etc.)**: TBD but the same shape.

Per-process state (in-memory counters, last-failure timestamp, etc.)
is the right granularity for chess-coach's volumes. Cross-process
state (Redis) would add operational complexity for no real benefit
when one process serves one user at a time.

## The four-file diff

1. **New module** `services/chess_coach/<thing>/protection.py` (~225 lines):
   - `TokenBucket`: classic refill-bucket; non-blocking `try_acquire()`;
     starts full, drains on call, refills at configured rate.
   - `CircuitBreaker`: 3-state (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
     Trips OPEN after N consecutive failures, holds for
     `cooldown_seconds`, then admits a single HALF_OPEN probe before
     resuming normal traffic. Single-shot probe (no thundering herd).
   - `ProtectionRegistry`: per-backend singleton instances of (bucket,
     breaker); module-level; resets on container restart.
   - Env-var configuration per backend, all optional with sensible
     defaults. Garbage values fall back to defaults with a WARNING log
     (typo-proof: a bad env var must NOT brick the route).

2. **Adapter dispatcher** change in
   `services/chess_coach/<thing>/adapter.py`:
   - Add a new `_predict_<backend>_protected(image_png_bytes)`
     wrapper that gates calls through the bucket and breaker.
   - Update `_REGISTRY["<backend>"]` to point at the protected wrapper.
   - The wrapped `_predict_<backend>` body is unchanged (still does
     the real work: httpx POST, JSON parse, etc.).
   - Module docstring updated to document the protection contract
     and the `rate_limit:` / `circuit_open:` error-string conventions.

3. **Unit tests** `tests/unit/test_<thing>_protection.py` (NEW, ~17 tests):
   - TokenBucket behavior in isolation (starts full, drains, refuses zero config).
   - CircuitBreaker state machine in isolation (CLOSED -> OPEN -> HALF_OPEN -> CLOSED; single-shot probe).
   - ProtectionRegistry per-backend isolation (different backends get independent state).
   - Env-var wiring + invalid-env fallback (garbage value -> WARNING log + default).

4. **Integration tests** in `tests/integration/test_<thing>_backend.py`:
   - Add a new `Test<Thing>Protection` class with 3 tests:
     - rate-limit returns structured error WITHOUT invoking the
       network (load-shedding case).
     - circuit breaker opens after N consecutive failures,
       short-circuits subsequent calls without network access.
     - circuit breaker recovers on HALF_OPEN probe success after cooldown.
   - Existing dispatcher tests are unchanged and still pass; the
     rate-limit / circuit-breaker protections apply transparently.

## The wrapper pattern (the only piece that's actually reusable)

```python
async def _predict_<backend>_protected(image_png_bytes: bytes) -> OcrResult:
    registry = get_protection_registry()
    if not registry.bucket_try_acquire("<backend>"):
        return OcrResult(None, 0.0, "rate_limit:<backend>:bucket_empty")
    if not registry.breaker_should_allow("<backend>"):
        return OcrResult(None, 0.0, "circuit_open:<backend>:cooldown")
    result = await _predict_<backend>(image_png_bytes)
    if result.error is None:
        registry.breaker_record_success("<backend>")
    else:
        registry.breaker_record_failure("<backend>")
    return result
```

Order matters: rate-limit check FIRST (shed load before testing
upstream), breaker check SECOND.

The protections NEVER raise. A denied request becomes a structured
`OcrResult` error. The route surfaces that as a per-page
`DiagramResult.issue` string — no HTTP 5xx for the whole request
just because one page got rate-limited.

## Env var contract (per backend)

```
CHESS_COACH_<THING>_<BACKEND>_RPS          default 1.0   sustained req/s
CHESS_COACH_<THING>_<BACKEND>_BURST        default 5     bucket capacity
CHESS_COACH_<THING>_<BACKEND>_CB_THRESHOLD default 5     consecutive failures to trip
CHESS_COACH_<THING>_<BACKEND>_CB_COOLDOWN  default 120.0 seconds before half-open probe
```

Naming convention: `CHESS_COACH_<THING>_<BACKEND>_*` (not
`CHESS_COACH_<BACKEND>_*` as the original BBF-68.2 handoff suggested)
so future backends under different `<THING>` modules get their own
config namespace.

## When to use this pattern

| Symptom in the codebase | Use ProtectionRegistry? |
|---|---|
| External service has no SLA / API key | YES — load shedding |
| External service returns 429s under burst | YES — rate limit |
| External service has occasional 5xx | YES — circuit breaker |
| External service is local / always-up | NO — add it later when needed |
| One-off script call | NO — overhead not worth it |
| Hot path with sub-100ms latency budget | MAYBE — in-process state adds ~0 latency but profile first |

## When NOT to use this pattern

- **State that needs to survive container restart.** The registry is
  in-process; a container restart resets it. If the upstream service
  is briefly flaky AT container boot, the bucket starts full and the
  breaker starts CLOSED — which is what you want, but it means the
  breaker won't remember "I tripped 5 minutes ago." Cross-process
  state (Redis) is the answer for that case.
- **Per-user rate limits.** The registry is global per backend. If
  you need per-user fairness, you need a different data structure
  (e.g. `dict[user_id, TokenBucket]`).

## When in doubt

Read `services/chess_coach/pdf_ocr/protection.py` on `main` at
`87ed28f` (BBF-68.2). The chess-coach codebase has the canonical
implementation; copy the structure and adapt the names.

## Related

- `references/post-audit-measurement-spike.md` — the gate before any
  BBF that names an external dep
- `references/route-handler-integration-tests.md` — for testing
  wrappers that touch the route layer
- `chess-coach-bbf-sprint` skill v0.7.36 (BBF-68.2 ship pattern)
- `CHANGELOG.md` under `[unreleased] - BBF-68.2`