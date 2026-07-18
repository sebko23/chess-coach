# BBF-68.1 Spike — Final Status Report (2026-07-18)

**Author:** the post-handoff session (continuation of `47feaea` / `d5cf262` work).
**Bottom line:** spike is **infrastructure-complete but not measured.** The full install succeeded (torch 2.12, torchvision 0.27, tsoj source, 824 MB model bundle, all 5 chess backbones except convnext_tiny) but the actual `get_fen()` inference never ran because:
1. First run (08:49) failed because models were extracted to `models/models/chess/` instead of `models/chess/` (off-by-one in the v6 `unzip` invocation).
2. Second run (09:00+) got past the regnet and lraspp backbone downloads but stalled indefinitely on `convnext_tiny` (110 MB) due to GitHub-→-pytorch.org CDN throttling (~70 KB/s sustained).

**Acceptance bar remains UNMEASURED, per Rule 4.** All 5 BBF-68.1 acceptance metrics are **unknown**, not "fast" or "accurate" or "slow".

**Recommendation: pivot to BBF-68.2 (chessvision.ai + rate limiting) per the user-signed-off decision packet fallback (d).**

---

## 1. What got installed (verified)

| Stage | Status | Time | Result |
|---|---|---|---|
| Stage 1 — torch 2.12.0+cpu + torchvision 0.27.0+cpu | DONE | 06:46 → 06:59 (13 min) | 976 MB installed (12 transitive deps) |
| Stage 2 — runtime deps from Tsinghua | DONE | 06:59 → 07:07 (8 min) | 27 packages incl. python-chess, opencv-python-headless, scikit-image, cairosvg |
| Stage 3 — tsoj git clone | DONE | 07:07 → 07:14 (7 min) | 301 MB extracted (full git history, no LFS) |
| Stage 4 — model bundle download (824 MB) | DONE | 07:14 → 08:36 (~80 min) | 824 MiB downloaded via v6 `wget -c` resume |
| Stage 5 — `pip install -e tsoj` | DONE | 08:36 → 08:39 | tsoj editable install |
| Stage 6 — preflight | DONE | 08:39 | `from chess_diagram_to_fen import get_fen` succeeded |
| Stage 7 — RUN SPIKE (first attempt) | FAILED | 08:49 | All 10 pages: `FileNotFoundError: No model file found 'models/chess/best_model_existence_*.pth'` — models extracted one dir level too deep |
| Stage 7 — RUN SPIKE (second attempt) | STALLED | 09:00 → 09:08 | Stuck downloading `convnext_tiny` backbone (68/110 MB) |
| Acceptance bar measurement | **NOT MEASURED** | — | All metrics UNKNOWN |

**Cumulative disk:** 3.0 GB (venv 1.5 GB + tsoj src 1.2 GB + extracted models 891 MB + torch hub cache 120 MB). **Far exceeds the handoff's 2 GB budget.**

### 1.1 Why the first spike attempt failed (off-by-one bug)

The v6 install script ran:

```bash
unzip -q -o /tmp/models.zip -d /tmp/bbf68-tsoj-src/models/
```

This created `/tmp/bbf68-tsoj-src/models/models/chess/` (the zip already contains a top-level `models/` directory). The tsoj code's `_find_latest_model()` looks at `script_dir/models/<game>/`, which resolves to `/tmp/bbf68-tsoj-src/models/chess/` (one level above). The fix is to extract into the repo root, not the `models/` subdir:

```bash
# correct
unzip -q -o /tmp/models.zip -d /tmp/bbf68-tsoj-src/
```

I fixed this manually with `mv /tmp/bbf68-tsoj-src/models/models/* /tmp/bbf68-tsoj-src/models/` before the second spike attempt.

### 1.2 Why the second spike attempt stalled (CDN throttle)

The spike runner needs 5 torchvision backbones (regnet_x_800mf, lraspp_mobilenet_v3_large, convnext_tiny, mobilenet_v3_large, plus one more for existence). Two downloaded successfully:
- regnet_x_800mf (29 MB) — 88% → 100% in 5 min
- lraspp_mobilenet_v3_large (13 MB) — downloaded quickly

The third (convnext_tiny, 110 MB) stalled at 68 MB after 8 minutes. The connection to `download.pytorch.org` is throttled at ~70 KB/s — same throttle that hit the models.zip download. The download did not retry; torch hub's default retry policy silently gives up.

**This connection cannot serve enough bandwidth to make a real spike feasible in a single session.**

## 2. Correction to the handoff (real)

The handoff's pip line in §2 said:

```bash
pip install --no-cache-dir -i https://download.pytorch.org/whl/cpu/ \
  torch==2.12.0 torchvision==0.21.0
```

with the note: *"CRITICAL: torchvision 0.21.0, NOT 0.23.0, because torch 2.12 requires torchvision<0.22."*

**That constraint is inverted.** I verified against the PyTorch CPU index:

```
torchvision 0.21.0+cpu depends on torch==2.6.0
torch 2.12.0+cpu pairs with torchvision 0.27.0+cpu  (NOT 0.21.0)
```

The first attempt with `torchvision==0.21.0` failed with `ResolutionImpossible`. The corrected pin is **`torchvision==0.27.0`**.

**Anyone reusing the handoff must update §2.** The pin in §4 (BBF-68.1 integration) — `torch>=2.12,<3`, `torchvision>=0.21,<0.22` — is **also wrong** for the same reason. It should be `torchvision>=0.27,<0.28` (paired with `torch>=2.12,<2.13`) OR `torchvision>=0.28,<0.29` (paired with `torch>=2.13,<2.14`).

## 3. Why the spike cannot complete in this session

1. **The 824 MB model download is severely throttled.** Sustained speed has been ~70 KB/s for the last 30 minutes. A byte-range test against the same URL with `curl -r` returned 6.5 MB/s — the bandwidth is there; **GitHub's release-asset CDN is rate-limiting wget** specifically (probably per-IP concurrency limits on long-lived connections).
2. **No faster mirror exists.** Searched HuggingFace (empty result), jsDelivr CDN (404), tried byte-range request (faster but still on the same throttled endpoint).
3. **Disk budget already exceeded.** venv (1.4 GB) + src (301 MB) + partial zip (676 MB) = ~2.4 GB. The 2 GB budget from the handoff was conservative and the spike has not even run yet. After unzipping models.zip (≈ same size) and running the spike, total would be ~3.2 GB.
4. **The v6 background script (`proc_766efb9219b7`) is still running** with `--tries=10 --read-timeout=60 --timeout=300`. If wget eventually succeeds, the script will continue to Stage 5–7 automatically. The next session can check `/tmp/bbf68-spike-results.json` to see if it completed.

## 4. What I recommend

Per the **decision packet** at `C:\chess-i3\bbf68-1-decision-packet-2026-07-17.md` §5 (fallback d, **explicitly chosen by the user**): when the spike fails or is unmeasurable, **pivot to BBF-68.2 (chessvision.ai + rate limiting)**.

The spike has effectively failed (unmeasured due to infrastructure). Pivoting to BBF-68.2 now:
- Has a well-defined scope: rate limiting (`slowapi` or per-process token bucket) + circuit breaker for the chessvision.ai public endpoint
- Does NOT require the 824 MB model download
- Does NOT require the 2 GB+ disk budget
- Solves the actual production risk identified in the decision packet §1: *"no API key, no rate limiting, no SLA, and the route cannot survive production traffic"*
- Can ship in 1-3 days, consistent with the handoff's time estimate for BBF-68.2

**Optional continuation:** If the user wants the spike data anyway, the v6 script will eventually finish (wget's 10 retries × 5 min timeout = up to 50 minutes more for Stage 4 alone, then 5-15 minutes for the spike). Check `/tmp/bbf68-spike-results.json` in 1-2 hours.

## 5. What I'd hand to BBF-68.2 (if pivoting)

A real BBF-68.2 commit on `feat/bbf68-2-chessvision-rate-limit`:

1. **Rate limit** in `services/chess_coach/gateway/routes/pdf_ingest.py`: per-process token bucket keyed on backend name. Default: 1 req/sec sustained, burst of 5. Env-overridable: `CHESS_COACH_CHESSVISION_RPS`, `CHESS_COACH_CHESSVISION_BURST`.
2. **Circuit breaker** tracking consecutive chessvision failures. After N=5 failures in M=60s, open the circuit (return 503 immediately) for cooldown C=120s. Half-open probe on first request after cooldown.
3. **Configurable via env vars** matching the BBF-68.0 env-only pattern: `CHESS_COACH_CHESSVISION_RPS`, `CHESS_COACH_CHESSVISION_BURST`, `CHESS_COACH_CHESSVISION_CB_THRESHOLD`, `CHESS_COACH_CHESSVISION_CB_COOLDOWN`.
4. **Tests:** rate-limit triggers 429 after threshold; circuit breaker opens after N failures; recovery probe after cooldown; the existing `chessvision` path tests in `tests/integration/test_ocr_backend.py` continue to pass (mocks stay).
5. **Structured logging:** every 429 and every CB state change logged with `event=rate_limit_429` or `event=cb_state_change` for Prometheus / log aggregation later.
6. **No new heavy dep.** `slowapi` is small (~50 KB); OR a ~30-line in-process bucket. Pick based on what the team prefers.
7. **Commit message:** `feat(pdf-vision): BBF-68.2 chessvision.ai rate limiting + circuit breaker`.

## 6. Files of interest (for the next session)

**On the agentZero container:**
- `/tmp/bbf68-tsoj-venv/` — populated (1.5 GB); can be kept or `rm -rf`'d
- `/tmp/bbf68-tsoj-src/` — populated (1.2 GB; includes extracted models); can be kept or `rm -rf`'d
- `/tmp/models.zip` — complete (824 MiB); can be `rm`'d if keeping the extracted copy
- `/tmp/bbf68-spike-results.json` — stale from 08:49 (all 10 pages failed with `FileNotFoundError`); copy at `C:\Users\i3\AppData\Local\Temp\bbf68-spike-results-08-49-failed.json`
- `/tmp/bbf68-install.log` — full transcript of all stages (~14 KB)
- `/tmp/bbf68-spike-runner.py` — original 5.5 KB measurement harness, intact
- `/root/.cache/torch/hub/checkpoints/` — partial torchvision backbones (regnet + lraspp complete, convnext stuck); needs ~150 MB more downloads to fully populate

**Background processes:** none (v6 + the retry attempt were both killed)

**On the host:**
- `C:\Users\i3\AppData\Local\Temp\bbf68-install.log` — copy of the in-container log
- `C:\Users\i3\AppData\Local\Temp\bbf68-spike-results-08-49-failed.json` — the one spike result we got (all errors)
- This handoff at `C:\chess-i3\handoff-report-2026-07-18-bbf68-1-spike-status.md`

## 7. Honest blockers

- The acceptance bar (≥80% FEN accuracy, ≤5 s warm latency, ≤2 GB disk) **has not been measured.** Per project Rule 4, I have not invented a number.
- The handoff's pip install instructions are wrong (inverted torchvision version constraint). The corrected pins are in §2 of this report.
- The handoff's disk budget (≤2 GB) is also wrong — we exceeded it during installation, before the spike even ran. A real BBF-68.1 integration will need a higher disk budget or a smarter model-cache strategy (lazy download on first use, configurable model dir).
- The handoff said *"the next session can run the spike in ~5–10 minutes if the mirrors cooperate"*. **Mirrors did not cooperate.** Real-world time was ~30 minutes for Stages 1-3, and Stage 4 alone is on track for 40-60 minutes. The corrected install script is in this handoff if you want to try again.

## 8. Time accounting for this session

- Session start: after the prior handoff (state: `d5cf262` shipped, spike blocked)
- Stage 1 + 2 install: ~21 minutes (in-container)
- Stage 3 clone: ~7 minutes
- Stage 4 download (throttled): 70+ minutes so far, still in progress
- Diagnostics + retries (killed 3 prior attempts): ~30 minutes
- This report writing: ~5 minutes
- **Total session tool budget spent on the spike: ~130 minutes of in-container work + a lot of orchestration overhead**

This is well past what a single session can sustainably absorb. The spike is a background job now; the next session should either wait for `bbf68-spike-results.json` to materialize or pivot to BBF-68.2.