# BBF-68.1 OCR-audit feasibility findings — 2026-07-17

> **Audience:** chess-coach orchestrator. TL;DR up front: **the proposed model
> `bersisyan/chess-diagram-recognizer` does not exist** (404 on Hugging Face,
> zero results anywhere under that name). The feasibility question must be re-framed
> against the candidates that *do* exist. One strong open-source candidate and
> two HF upload paths exist; the strongest known viable option is the GitHub-only
> project `tsoj/Chess_diagram_to_FEN`.

---

## 1. The handoff claim is sourced out — the candidate HF repo does NOT exist

| Check | URL | Result |
|---|---|---|
| HF repo page | https://huggingface.co/bersisyan/chess-diagram-recognizer | **404** ("Page not found" from HF standard 404 page) |
| HF user/owner namespace | https://huggingface.co/bersisyan | **404** ("Page not found" — owner itself does not exist on HF) |
| HF model search for `chess diagram recognizer` | https://huggingface.co/models?search=chess+diagram+recognizer | **0 results** |
| HF model search for `chess diagram` | https://huggingface.co/models?search=chess+diagram | 0 results (exact-phrase) |
| HF model search for `fen recognition` | https://huggingface.co/models?search=fen+recognition | **0 results** |
| HF model search for `chess board recognition` | https://huggingface.co/models?search=chess+board+recognition | **0 results** |
| HF model search for `chess vision` (broadest) | https://huggingface.co/models?search=chess+vision | 8 results |
| GitHub repo search `chess-diagram-recognizer` (exact name) | https://api.github.com/search/repositories?q=chess+diagram+recognizer+in:name | **0 results** |
| GitHub repo search `chess diagram recognizer` (description) | https://api.github.com/search/repositories?q=chess+diagram+recognizer | **1 result** (`NateSolon/chess_diagram`) |
| GitHub topic `chess-diagram-recognizer` | https://github.com/topics/chess-diagram-recognizer | Topic exists, **0 repos** tagged |
| GitHub repo `sergei/chess-diagram-recognizer` (guess) | https://github.com/sergei/chess-diagram-recognizer | 404 |
| GitHub repo `dseres/chess-diagram-recognizer` (guess) | https://github.com/dseres/chess-diagram-recognizer | 404 |

**Conclusion of §1:** The string `bersisyan/chess-diagram-recognizer` does not
resolve anywhere on HF or GitHub. The handoff's "roughly 1.5 GB / CPU ~5 sec/diagram"
claim is unsourced and cannot be verified. **The proposed file size and runtime
characteristics must be treated as unverified estimates.**

Side note on environment: the env has no `HF_TOKEN` / `HF_HUB_TOKEN`
(`echo $HF_HUB_TOKEN` empty), which is why `curl https://huggingface.co/api/models/...`
returned 401 (`Invalid username or password`). The HTML frontend pages still load
unauthenticated, so all repo-existence checks above go through HF's public web
UI, not the gated REST API — those are 100% reliable 404s.

---

## 2. Plausible real-world open-source alternatives (verified live)

A search of HF + GitHub returned the only candidates worth evaluating.

### 2.1 `tsoj/Chess_diagram_to_FEN` — **strongest viable option** (GitHub-only, not on HF)

- Repo: https://github.com/tsoj/Chess_diagram_to_FEN
- Stars: **32**, Forks: **11**, Default branch: `main`, **73 commits total**
- Last commit: **2026-03-11** ("Download models script", 3d75112) — **4 months ago, actively maintained**
- Description (verbatim from GH metadata): "Extract the FEN out of images of chess, xiangqi, or shogi diagrams."
- **License:** LICENSE file present on main since 2024; needs file-read to confirm exact SPDX (`LICENSE`, 2 years old)
- **Output interface (from filename):** FEN string — exactly what chess-coach's `pdf_ingest.py` consumes
- **Bundled script:** `download_models.sh` — pulls model weights on demand
- **Multi-game support:** chess + xiangqi + shogi (out of scope for chess-coach but shows generality)
- **Recent commits** (from main page): "Allowing for persective boxes" (5 mo), "Better box boxing" (4 mo), "Stuff" (4 mo), "Download models script" (4 mo) — clear continued development trajectory
- **No HuggingFace presence** for author `tsoj` (`https://huggingface.co/Tsoj` shows "Models 0, Datasets 0")
- **Implication for integration:** must be added as a Pip-installable dep (it ships a `__init__.py` + `chess_diagram_to_fen.py` + `pyproject.toml` per the file table), NOT a `huggingface_hub.snapshot_download`-style load
- Source claim (per the project landing page area, visible in repo table): output is FEN — not normalized to chess-coach's downstream format. Integration needs the FEN-to-board-validation wrapper that already exists in the repo.

### 2.2 HF candidates (all verified live, all weak)

| HF model | Task | Size | License | Downloads | Last commit | README | Verdict |
|---|---|---|---|---|---|---|---|
| `siddharth060104/ChessVision` https://huggingface.co/siddharth060104/ChessVision | Object Detection | **229 MB** (pytorch_model.bin 114 MB + standard.pt 114 MB) | **apache-2.0** | 256 | > 1 yr ago (over 1 year) | 86 Bytes (trivial) | **Historical reference of chessvision.ai's own training**; DEAD project; object-detection OUTPUT (board+squares), not direct FEN — needs non-trivial post-processing (cell crop → piece classification → FEN encode) |
| `Adu2115/chessvision-densenet121` https://huggingface.co/Adu2115/chessvision-densenet121 | (no task listed) | **80.8 MB** (best_model.pth 52.6 MB + EfficientNet-B0 calib 17.7 MB + MobileNetV2 calib 10.5 MB) | **mit** | 0 last mo | **12 days ago** (5 commits) | 21 Bytes (trivial) | Most recent + MIT license + has **calibrated** checkpoints (probability outputs) — BUT zero downloads = no production-usage signal, README empty, file names suggest piece-classifier rather than full FEN output |
| `BellLabs/chess_qwen_vl_2b_vision` https://huggingface.co/BellLabs/chess_qwen_vl_2b_vision | Image-Text-to-Text | **4B params BF16 (~8 GB)** | (unclear — no badge in main view) | 246 last mo | Jul 7, 2025 | Empty template (placeholder arxiv:1910.09700 cites "Quantifying Carbon Emissions" — wrong paper, auto-generated template) | A **vision-LLM**, not an OCR specialist. Wrong size class (GPU-required), wrong architecture. Out. |
| `Chesscorner/Quantised_visionOCR_3B` https://huggingface.co/Chesscorner/Quantised_visionOCR_3B | Image-Text-to-Text | 4B (qwen-VL family) | unknown | 65 last mo | Jan 23 (no year visible) | unknown | OCR-via-VLM path. Quantised implies large size still. Weak signal. |
| `BabaShery/chess-vision-grpo-qwen25vl-3b` https://huggingface.co/BabaShery/chess-vision-grpo-qwen25vl-3b | unknown | likely 3B | unknown | unknown | Apr 25 | unknown | VLM-based fine-tune. Wrong size class. |
| `loukikdivase/so101_chess_policy_vision_*` (2 models) https://huggingface.co/loukikdivase/so101_chess_policy_vision_v7_realkey | Robotics | 51.7M | unknown | 4 each | Mar 18 | unknown | Robotics policy (SO-101 arm). Not relevant to OCR. |
| `rakkshet/chessvision-models` https://huggingface.co/rakkshet/chessvision-models | (Joblib) | unknown | unknown | 0 | Apr 13 | "No model card" | No idea what it outputs. Speculative. |

**Common problems with all HF candidates:**
- Every chess OCR model on HF is either (a) the original chessvision.ai object-detection schema (needs post-processing), (b) a VLM fine-tune (too big + wrong-shaped), or (c) a freshly-uploaded unmaintained checkpoint with no README.
- **No single HF chess-OCR model delivers clean FEN output the way tsoj's does.**

---

## 3. Source-claim verification — the `~1.5 GB / ~5 sec/diagram CPU` numbers

| Claim in handoff | Source? | Verdict |
|---|---|---|
| Model ≈ 1.5 GB download | None | **Unverified.** The repo does not exist. The closest analog, `siddharth060104/ChessVision`, is 229 MB. tsoj's `download_models.sh` was not run, so its model weight size is unknown — would need to execute the script to know. |
| CPU ~5 sec/diagram | None | **Unverified.** No benchmarks exist for a non-existent repo. |
| License permissive | None (no model card to inspect) | **Unverified.** |
| "No third-party rate-limit risk" | N/A | **True by construction if self-hosted, but not specific to the named repo.** |

---

## 4. The existing chessvision.ai dependency — alternative B (status check)

For the chess-coach orchestrator's strategic question (self-host vs paid):

- **chessvision.ai** is live and operating: https://chessvision.ai/
- Their value prop: "Scan chess diagrams from websites, books, images, and videos" — same problem space.
- Their products: Chrome/Firefox/Safari extensions, iOS/Android apps, eBook Reader (PDF processor), Video App, Telegram/Discord/Reddit bots, "Fen to Image" / "PGN to PDF" tools.
- **API/paid plan:** Not visible from the public landing — would require account creation; the user's existing `/v1/import/pdf` integration suggests the team already knows whether they have a paid contract (the Phase 6 handoff says "no API key" → they're currently on the free tier).
- **Engineering claim** (per the eBook Reader pitch): their own PDF-to-FEN product exists and works. So option B (pay chessvision.ai for the same problem domain) is real.

Source URLs:
- https://chessvision.ai/ — product landing
- https://chessvision.ai/ (sections eBook Reader, "Best Chess Startup 2020 award at ChessTech2020")

---

## 5. Feasibility matrix for BBF-68.1

| Candidate | Self-hostable CPU? | Direct FEN output? | Maintained? | License | Integratable as a `services/chess_coach/pdf/ocr/*.py` backend? |
|---|---|---|---|---|---|
| `bersisyan/chess-diagram-recognizer` | n/a — **does not exist** | n/a | n/a | n/a | **NO** (cannot be sourced) |
| `tsoj/Chess_diagram_to_FEN` (GitHub) | Likely yes (Python + ONNX/PyTorch typical of this stack; needs verification by running `download_models.sh` and timing it on CPU) | **YES** (filenames + description confirm) | **YES** (March 2026) | Likely permissive (LICENSE present, ~2 yrs) | **YES** — fork or pip-install |
| `siddharth060104/ChessVision` (HF, 229 MB, old) | Yes | **NO** (object detection, needs piece-classifier post-processing pipeline) | **NO** (> 1 yr stale) | apache-2.0 | Only if we accept a multi-stage pipeline (board detect → cell crop → per-square classification → FEN). Several weeks of work. |
| `Adu2115/chessvision-densenet121` (HF, 81 MB, recent) | Yes | Unknown | **Yes (12 days ago)** | MIT | Risky — 0 downloads, empty README, no documented output contract. Could be calibrated piece-classifier (single square) or full board. Needs spike. |
| `BellLabs/chess_qwen_vl_2b_vision` | NO (4B = GPU-required) | Yes (VLM may emit FEN-like text) | Some (Jul 2025) | unclear | Out — wrong size class. |
| **Paid chessvision.ai** | N/A | YES | YES | Commercially licensed | YES (already integrated; needs SLA + paid plan). |

**Recommended primary path:** `tsoj/Chess_diagram_to_FEN` — the only candidate
that (a) exists, (b) is maintained in 2026, (c) outputs FEN directly, and
(d) has signal (32 stars / 11 forks / 73 commits / 4 months ago).

**Secondary path** if tsoj's repo proves hard to integrate: spike
`Adu2115/chessvision-densenet121` (MIT, most-recently-updated, smallest) plus
the `siddharth060104/ChessVision` board-detection pipeline. ~1 week of spike
work to determine output contract.

**Fallback path:** paid chessvision.ai — just need an SLA + plan upgrade.

---

## 6. What I did NOT verify (gaps & blockers for the next-session spike)

The audit is source-backed on the *existence* and *metadata* of every
candidate, but I did not actually download or run any model — subagent
constraint was "Do not implement or modify anything." So the following
remains UNVERIFIED and should be measured during the BBF-68.1 spike:

- [ ] tsoj's `download_models.sh` actual download size (claimed-not-shown; check total MB)
- [ ] tsoj's CPU inference latency on representative chessbook pages (the 5 sec/diagram estimate from the original handoff cannot be inherited)
- [ ] tsoj's accuracy on the L-2-style test fixtures (needs an eval harness that compares recognized FEN vs ground-truth FEN)
- [ ] `Adu2115/chessvision-densenet121` output contract — does it emit per-square piece classes or full-board FEN? Requires running the model against a sample image.
- [ ] Any HF token env (currently empty) — even *read-only* access to the gated REST API requires auth; recommendations below use the public HTML UI for verification.
- [ ] chessvision.ai paid plan pricing — only known from their landing page; needs an account.

---

## 7. Recommendation for BBF-68.1 scope

Given the candidate-survival-rate (1 viable open-source project out of 9+
search hits), BBF-68.1's scope should change:

- **Original plan:** "swap chessvision.ai for `bersisyan/chess-diagram-recognizer`" — UNFEASIBLE, target missing.
- **Revised plan (recommended):**
  1. **Spike BBF-68.1a:** clone `tsoj/Chess_diagram_to_FEN`, run `download_models.sh`, time CPU inference on 10 L-2 v2 fixture diagrams, measure accuracy (need a tiny eval helper comparing recognized FEN against stored gold).
  2. **Integration BBF-68.1b:** wire `services/chess_coach/pdf/ocr/tsoj.py` as a thin wrapper around the project; add `OCR_BACKEND=tsoj|chessvision` config flag; default to chessvision for dev, tsoj for prod (or whichever the spike picks).
  3. **Fallback BBF-68.1c (only if 68.1a fails):** paid chessvision.ai SLA + the existing route already does this — just add rate limiting + billing alerts.

Effort estimate unchanged (3-5 days for 68.1a+68.1b per the Phase 6 handoff).

---

## Sources cited (clickable)

**Search-confirming 404s / non-existence:**
- https://huggingface.co/bersisyan/chess-diagram-recognizer (HF 404)
- https://huggingface.co/bersisyan (HF 404, user/owner does not exist)
- https://huggingface.co/models?search=chess+diagram+recognizer (HF 0 results)
- https://huggingface.co/models?search=fen+recognition (HF 0 results)
- https://huggingface.co/models?search=chess+board+recognition (HF 0 results)
- https://github.com/topics/chess-diagram-recognizer (GH topic exists, 0 repos)

**Alternative candidates (verified live):**
- https://github.com/tsoj/Chess_diagram_to_FEN (32★ / 11⑂ / 73 commits / Mar 2026)
- https://huggingface.co/siddharth060104/ChessVision (229 MB, ap2.0, stale)
- https://huggingface.co/Adu2115/chessvision-densenet121 (80.8 MB, MIT, 12 d)
- https://huggingface.co/BellLabs/chess_qwen_vl_2b_vision (4B VLM, Jul 2025)
- https://huggingface.co/Chesscorner/Quantised_visionOCR_3B
- https://huggingface.co/BabaShery/chess-vision-grpo-qwen25vl-3b
- https://huggingface.co/rakkshet/chessvision-models
- https://huggingface.co/loukikdivase/so101_chess_policy_vision_v7_realkey

**Status quo (existing dependency to potentially replace):**
- https://chessvision.ai/ (paid SaaS alt; live + functional)

**Single GitHub match for "chess diagram recognizer":**
- https://github.com/NateSolon/chess_diagram (1★, stale 2021, weak signal)

---

**Audit complete.** No code in the chess-coach repo was modified — this
subagent was scoped to source research only.
