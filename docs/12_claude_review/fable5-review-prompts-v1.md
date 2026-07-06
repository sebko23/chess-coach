# Fable-5 External Review Prompts — CHESS COACH (v1, first draft)

**Status**: First draft. Owner: Agent Zero. Date: 2026-07-07.
**Target model**: Fable-5 (frontier; used via its own chat window — NOT as the chess-coach LLM).
**Budget**: 2 messages / 5 hours on free tier. These prompts are designed to be **self-contained**: Fable-5 has no filesystem access, no tool calls, no internet, so everything it must reason on has to be pasted into the prompt. A local Python builder (Section 5) assembles that context for free.
**Precedent**: `docs/12_claude_review/claude-review-package.md` (the Claude.ai review of 2026-05-18) and its response in `docs/13_review_response/response-to-review.md`. We are explicitly trying to avoid the drift and gaps that review flagged.

---

## 1. What this file contains

| # | Section | Purpose |
|---|---|---|
| 1 | You are here | Meta + how to use |
| 2 | Chess-coach in one screen | Context Fable-5 needs before either prompt |
| 3 | **Prompt 1 — EXAMINE** | Architecture + code audit (no suggestions yet) |
| 4 | **Prompt 2 — RECOMMEND** | Concrete fixes + ideas, cites Prompt 1's findings |
| 5 | Local mega-prompt builder (Option B from fable.txt) | The script that builds Prompt 1's `<file_index>` and `<relevant_files>` blocks |
| 6 | Usage checklist | Step-by-step for the 2-message budget |
| 7 | What Fable-5 does **not** see | Explicit blindspots so the human stays accountable |
| 8 | Open questions for v2 | What we'd change after this run |

---

## 2. Chess-coach in one screen (paste into BOTH prompts as `<project_context>`)

> **CHESS COACH** is a production-grade chess coaching platform: Tauri desktop shell + Python FastAPI gateway backend, fusing Stockfish / Maia / lc0 engine analysis with a grounded LLM narrator (OpenRouter; current primary `z-ai/glm-5.2`, fallback `z-ai/glm-4.5-air`). State in SQLite, vectors in Qdrant, PDFs via vision pipeline (Phase 6). The frontend fork is en-croissant (GPL — compliance boundary). Project is mid-Phase-1 (foundation + engine + narration done; Phase 2 starts engine expansion + cloud cache). 14-module decomposition (post-2026-05-18-review, 5 merged). Five external reviews already on file. Architecture, roadmap, risks, security, performance, repo structure, ADRs and one protocol spec (`specs/v1.0/chess-coach-protocol-v1.md`) all live under `docs/`. The desktop is React + Zustand; the backend is async FastAPI services. License: project is MIT-bound for original code, en-croissant fork area is GPL — keep them isolated by directory (per ADR-0004). The human user is the legal/budget owner; Agent Zero is the autonomous architect-engineer.

Treat this as the **ground truth preamble** — both prompts below must include it as `<project_context>...</project_context>` near the top.

---

## 3. Prompt 1 — EXAMINE  (architecture + code audit, no fixes yet)

### 3.1 System block (paste verbatim as the message's `system`)

```
You are a senior software architect and code auditor.

You are reviewing a mid-sized monorepo: a Tauri desktop chess-coaching app
with a Python FastAPI gateway backend. You will NOT be able to call tools
or read files yourself — everything you need is in this message. Your
job is to reason carefully over what is given and produce a structured
review.

Hard rules:
  R1. Cite every concrete claim with the form `<file>:<line>` if a file
      is given, otherwise `[context:<section>]`. If you cannot ground
      a claim, mark it `[ungrounded]` and lower its confidence.
  R2. Do not invent features, file paths, commits, or line numbers.
      If you are guessing, say so explicitly.
  R3. Output exactly the 7 sections listed under "Required output".
      No prose before or after.
  R4. Bias toward *specific* findings over generic advice.
      "Add error handling" is useless; "wrap the call at
      services/chess_coach/engine_orch/spawn.py:88 in try/except
      OSError because fork() can EMFILE on Windows" is useful.
  R5. Treat the prior review (`<prior_review_summary>` block) as a
      baseline: have the issues it flagged actually been addressed in
      the code/docs we now have? Be honest — say "FIXED", "PARTIAL",
      "STILL OPEN", or "WORSE".
  R6. If two sources disagree (e.g. ADR vs README vs code), quote both
      and say which you trust more and why.

Required output (in this exact order):

  1. EXECUTIVE_SUMMARY   (≤120 words, what is good, what is fragile)
  2. ARCHITECTURE_FINDINGS  (bulleted; module boundaries, IPC contracts,
                              gateway pattern, deployment topology)
  3. CODE_FINDINGS         (bulleted; one finding = one file:line)
  4. DOC_FINDINGS          (bulleted; contradictions between docs and
                              between docs and code)
  5. PRIOR_REVIEW_STATUS   (one row per item in <prior_review_summary>;
                              verdict: FIXED | PARTIAL | STILL OPEN | WORSE)
  6. RISKS_NOT_IN_DOCS     (anything risky that the docs do not flag)
  7. OPEN_QUESTIONS        (questions you cannot answer from the
                              supplied context — the human will fill these)
```

### 3.2 User block (paste the assembled mega-prompt here)

```
<project_context>
[PASTE THE "Chess-coach in one screen" BLOCK FROM SECTION 2]
</project_context>

<prior_review_summary>
[PASTE A 1-PARAGRAPH DIGEST OF docs/12_claude_review/claude-review-package.md
AND docs/13_review_response/response-to-review.md. Highlight the items
that were supposed to be FIXED — Fable-5 will check the code/docs to
verify. Aim for ~40 lines. If too long, drop items rated ALREADY-COMPLETE
in the response doc and keep the ones rated STILL-OPEN.]
</prior_review_summary>

<project_map>
[PASTE THE OUTPUT OF:  find /a0/usr/projects/chess_coach -maxdepth 3 \
  -not -path '*/venv/*' -not -path '*/node_modules/*' -not -path \
  '*/dist/*' -not -path '*/.git/*' -not -path '*/__pycache__/*' \
  -not -path '*/data/qdrant/*'  | sort   →   prune to depth-2 dirs
  and depth-3 files only. Cap ~200 lines.]
</project_map>

<file_index>
[PASTE THE BUILDER OUTPUT FROM SECTION 5.2 — the top ~12 files
ranked by relevance, with one-line summaries.]
</file_index>

<relevant_files>
[PASTE THE FILE BODIES, IN ORDER, EACH WRAPPED IN:
  <file path="relative/path.py">
  ...full file body...
  </file>

Truncate any file > 25 KB at the 400-line mark and append:
  [... truncated, 25K file, full content in repo at <path> ...]

Hard cap total <relevant_files> at ~80 KB.]
</relevant_files>

<logs>
[OPTIONAL. If a recent bug is in scope, paste the last 200 lines of
  /tmp/gateway.log OR the relevant pytest -v output OR a curl trace.
  Without logs, Fable-5 will treat runtime behaviour as "unknown".]
</logs>

<question>
Audit this codebase. Produce the 7-section review per the system prompt.
Focus on:
  - architectural drift between docs/01_architecture, docs/02_modules
    and the actual code under services/chess_coach/;
  - license boundary leaks between the en-croissant-fork directory
    (apps/desktop) and the MIT-bound original code;
  - the grounded-narration pipeline (services/chess_coach/narration +
    llm_router) — is it actually robust or is it leaking prompt-injection
    surface / hallucinated moves?
  - test coverage and golden-test gaps for the engine orchestrator
    and LLM router;
  - anything that would explode at Phase 8 (packaging) or under
    Tauri/PyInstaller frozen-mode constraints.
</question>
```

---

## 4. Prompt 2 — RECOMMEND  (concrete code + ideas, cites Prompt 1)

**This prompt must be sent as the SECOND message in the 2-message budget.**
It depends on Prompt 1's output being in the conversation history. Do **not**
include `<relevant_files>` again — Fable-5 already has them. The user block
below starts with `<prior_review_status>` containing Fable-5's own reply to
Prompt 1 (or the relevant subset).

### 4.1 System block (paste verbatim as `system`)

```
You are the same senior architect who produced the audit in the previous
turn. Now produce concrete, shippable recommendations.

Hard rules:
  R1. Every recommendation MUST cite one or more findings from your
      previous audit (use the finding IDs the human pasted into
      <prior_review_status>). No new findings here — just fixes.
  R2. For each recommendation give:
        ID         (e.g. REC-A1, REC-C7)
        Finding    (which audit finding this addresses)
        Why        (1–3 sentences)
        Change     (concrete: file path(s), function name(s),
                   short diff or full new code if small, OR a
                   precise enough description that a competent
                   engineer can implement without guessing)
        Risk       (what can break; how to roll back)
        Effort     (S/M/L with rough hours)
        Phase gate (which roadmap phase this should land in:
                   Gate-0 / Phase 1 / Phase 2 / ... / Phase 8)
  R3. Prioritise by (impact / effort). Show your ordering.
  R4. Where a recommendation requires a decision the human must make
      (license, vendor, budget, model choice), do NOT pick — list the
      2–3 reasonable options and the tradeoffs.
  R5. Stay grounded in the actual codebase. Do not propose libraries
      that contradict an existing ADR unless you flag the ADR conflict.

Required output (in this order):

  1. PRIORITISED_RECOMMENDATIONS_TABLE
     | ID | Finding | Phase | Effort | Impact | Risk |
     (10–20 rows, sorted by impact/effort)
  2. DETAILED_RECOMMENDATIONS
     (one section per ID, with Why/Change/Risk/Effort/Phase)
  3. CROSS_CUTTING_THEMES
     (2–5 themes that connect multiple findings — e.g.
      "observability is missing in 4 places")
  4. ADR_CONFLICTS
     (recommendations that contradict an existing ADR; the human
      will decide whether to amend or override)
  5. PHASE_PLAN_DELTAS
     (bulleted additions to docs/10_roadmap/phase-plan-v2.md —
      either new exit criteria or new tasks inside existing phases)
  6. IMMEDIATE_NEXT_3_ACTIONS
     (exactly 3, ≤1 day each, can be done in parallel, total < 1 day)
```

### 4.2 User block (paste verbatim, fill the variables)

```
<project_context>
[SAME "Chess-coach in one screen" BLOCK AS PROMPT 1 — KEEP IT IN]
</project_context>

<prior_review_status>
[PASTE FABLE-5'S REPLY TO PROMPT 1. If it's huge, paste ONLY:
   - the EXECUTIVE_SUMMARY,
   - the bulleted findings lists (sections 2–4 of its reply),
   - the RISKS_NOT_IN_DOCS section.
   Skip the OPEN_QUESTIONS section — they were answered implicitly
   by your recommendations.]
</prior_review_status>

<prior_roadmap>
[PASTE docs/10_roadmap/phase-plan-v2.md SECTIONS "Phase 1" THROUGH
 "Phase 3" ONLY — these are the gates your recommendations must land
 in. Skip Phase 4+ unless a finding explicitly drags forward.]
</prior_roadmap>

<question>
Produce concrete, shippable recommendations per the system prompt.
Constraints:
  - Stay inside the existing module decomposition (no 15th agent;
    the 14-agent debate was settled in 2026-05-18).
  - Do not propose a new orchestrator framework; Celery + Redis
    Streams is locked in per ADR-0001 and Phase 6 plan.
  - Do not propose switching the LLM provider away from OpenRouter
    (that's a deliberate cost-routing choice).
  - You MAY propose adding a *new ADR* if you find a gap; flag it in
    ADR_CONFLICTS and propose the ADR number.
  - You MAY propose pinning specific dependency versions if you spot
    a security/correctness risk, but call out the upgrade cost.
</question>
```

## 5. Local mega-prompt builder (Option B from fable.txt)


The Python script below is the "zero LLM cost" half of the strategy:
it assembles `<file_index>` and `<relevant_files>` locally so Fable-5
only spends its 2-message budget on actual reasoning. Save it as
`scripts/build_fable5_prompt.py` in the project root (helper, not
production code — keep it out of the install manifest).

### 5.1 `scripts/build_fable5_prompt.py`

```python
#!/usr/bin/env python3
"""Build a self-contained mega-prompt for Fable-5 from chess-coach.

Usage:
    python3 scripts/build_fable5_prompt.py \\
        --root /a0/usr/projects/chess_coach \\
        --question "Audit this codebase. Focus on grounded-narration
                    pipeline robustness and license-boundary isolation." \\
        --out /tmp/fable5_prompt1.txt

The output is the **user message** to send to Fable-5 (Prompt 1 from
docs/12_claude_review/fable5-review-prompts-v1.md, section 3.2). The
human pastes it after the system block.

No LLM calls. Pure local heuristic + grep.
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

IGNORE_DIRS = {".git", "venv", "node_modules", "dist", "build", "__pycache__",
               "data/qdrant", "data/sqlite", "data/engines",
               "apps/desktop/dist", "apps/desktop/src-tauri/target",
               ".pytest_cache", "chess_coach.egg-info"}
IGNORE_EXTS = {".pyc", ".pyd", ".so", ".dll", ".png", ".jpg", ".jpeg",
               ".gif", ".webp", ".ico", ".mp3", ".wav", ".ogg", ".ttf",
               ".woff", ".woff2", ".pdf", ".zip", ".tar", ".gz", ".bz2",
               ".pkl", ".faiss", ".bin", ".pb", ".onnx", ".lock",
               ".tsbuildinfo", ".map"}

# Hand-picked MUST-INCLUDE files for any Fable-5 audit of chess-coach.
# These are the project's load-bearing artefacts; without them the
# review is blind. Adjust per audit topic; keep short.
MUST_INCLUDE = [
    "docs/01_architecture/system-architecture.md",
    "docs/02_modules/module-decomposition.md",
    "docs/10_roadmap/phase-plan-v2.md",
    "docs/07_risk/risk-analysis.md",
    "docs/08_security/security-strategy.md",
    "docs/11_repo_structure/repository-structure.md",
    "docs/14_adrs/ADR-0001-async-sync-boundary.md",
    "docs/14_adrs/ADR-0004-license-posture.md",
    "specs/v1.0/chess-coach-protocol-v1.md",
    "services/chess_coach/llm_router/router.py",
    "services/chess_coach/llm_router/config.py",
    "services/chess_coach/narration/pipeline.py",
    "services/chess_coach/gateway/app.py",
    "services/chess_coach/gateway/routes/narration.py",
    "tests/unit/test_narration.py",
    "pyproject.toml",
]

SOFT_INCLUDE_DIRS = ["services/chess_coach", "libs/chess_coach", "docs", "specs"]

MAX_TOTAL_BYTES  = 80 * 1024   # hard cap on <relevant_files>
PER_FILE_BYTES   = 25 * 1024   # truncate any single file larger than this
PER_FILE_LINES   = 400         # keep first N lines of huge files


def is_ignored(p: Path) -> bool:
    s = str(p)
    for d in IGNORE_DIRS:
        if f"/{d}/" in s or s.endswith(f"/{d}"):
            return True
    if p.suffix.lower() in IGNORE_EXTS:
        return True
    if p.name.startswith(".") and p.name not in {".env", ".a0proj"}:
        return True
    return False


def tree(root: Path, depth: int = 3) -> str:
    out = []
    for p in sorted(root.rglob("*")):
        if is_ignored(p):
            continue
        rel = p.relative_to(root)
        if len(rel.parts) > depth:
            continue
        indent = "  " * (len(rel.parts) - 1)
        marker = "/" if p.is_dir() else ""
        out.append(f"{indent}{p.name}{marker}")
    return "\n".join(out)


def score(path: Path, keywords: set[str]) -> float:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0.0
    p = str(path).lower()
    s  = sum(3.0 for k in keywords if k in p)
    s += sum(text.lower().count(k) for k in keywords)
    if path.stat().st_size < 4_000:
        s *= 1.1
    return s


def read_truncated(path: Path, budget: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[unreadable: {e}]"
    if len(text.encode("utf-8")) <= budget:
        return text
    head = "\n".join(text.splitlines()[:PER_FILE_LINES])
    note = (f"\n\n[... truncated at {PER_FILE_LINES} lines; "
            f"{path.stat().st_size//1024} KB file in repo ...]")
    return head + note


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--question", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERR: {root} is not a directory", file=sys.stderr)
        return 2

    # Keywords from the question (len>3, lowercase, dedup)
    kw = {w.lower() for w in re.findall(r"[A-Za-z_]\w+", args.question)
          if len(w) > 3}

    # 1) MUST_INCLUDE first
    chosen: list[Path] = []
    seen: set[Path] = set()
    for rel in MUST_INCLUDE:
        p = root / rel
        if p.exists() and p.is_file() and not is_ignored(p):
            chosen.append(p)
            seen.add(p)

    # 2) Ranked soft candidates from soft dirs + docs/ + specs/
    candidates: list[Path] = []
    for d in SOFT_INCLUDE_DIRS:
        dpath = root / d
        if not dpath.is_dir():
            continue
        for p in dpath.rglob("*"):
            if not p.is_file() or is_ignored(p) or p in seen:
                continue
            candidates.append(p)
    ranked = sorted(candidates, key=lambda p: score(p, kw), reverse=True)

    # 3) Top up to budget
    total = sum(p.stat().st_size for p in chosen)
    for p in ranked:
        if total >= MAX_TOTAL_BYTES:
            break
        if p in seen:
            continue
        # Skip large irrelevant files; keep small structural ones
        if score(p, kw) <= 0 and p.stat().st_size > 8_000:
            continue
        chosen.append(p)
        seen.add(p)
        total += p.stat().st_size

    # 4) Assemble the user message
    parts: list[str] = []
    parts.append("<project_map>")
    parts.append(tree(root, depth=3))
    parts.append("</project_map>\n")

    parts.append("<file_index>")
    for p in chosen:
        rel = p.relative_to(root)
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            first_comment = ""
            for line in text.splitlines()[:10]:
                s = line.strip()
                if s.startswith("#") or s.startswith('"""') or s.startswith("'"):
                    first_comment = s.lstrip("#\"'").strip()[:120]
                    if first_comment:
                        break
            parts.append(f"- {rel}  ({p.stat().st_size//1024} KB)  "
                         f"\u2014 {first_comment or '(no header)'}")
        except Exception:
            parts.append(f"- {rel}  (unreadable)")
    parts.append("</file_index>\n")

    parts.append("<relevant_files>")
    remaining = MAX_TOTAL_BYTES
    for p in chosen:
        budget = min(remaining, PER_FILE_BYTES)
        body = read_truncated(p, budget)
        rel = p.relative_to(root)
        parts.append(f'<file path="{rel}">')
        parts.append(body)
        parts.append("</file>\n")
        remaining -= len(body.encode("utf-8"))
        if remaining <= 0:
            parts.append("[... remaining files omitted to stay under "
                         f"{MAX_TOTAL_BYTES//1024} KB cap ...]")
            break
    parts.append("</relevant_files>\n")

    parts.append("<question>")
    parts.append(args.question.strip())
    parts.append("</question>")

    args.out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size//1024} KB, "
          f"{len(chosen)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 5.2 Build and verify

```bash
# 1. Build Prompt 1's user message (~30 s locally)
python3 scripts/build_fable5_prompt.py \\
    --root /a0/usr/projects/chess_coach \\
    --question "Audit this codebase. Focus on grounded-narration
                 robustness, license-boundary isolation, engine
                 orchestrator error paths, and Phase 8 packaging risks." \\
    --out /tmp/fable5_prompt1.txt

# 2. Inspect size and file list
wc -c /tmp/fable5_prompt1.txt
grep -c '^<file path=' /tmp/fable5_prompt1.txt

# 3. Open Fable-5's chat, paste:
#    - system block from section 3.1 (as `system`)
#    - user block from /tmp/fable5_prompt1.txt, with the
#      <project_context> and <prior_review_summary> blocks
#      manually prepended at the top

# 4. Wait for Fable-5's reply. Copy it verbatim to:
#    /tmp/fable5_reply1.md

# 5. Build Prompt 2 by hand (no script — it is short). Use section 4.2
#    with <prior_review_status> filled from /tmp/fable5_reply1.md
#    and <prior_roadmap> filled from docs/10_roadmap/phase-plan-v2.md.
```

---

## 6. Usage checklist (do this in order)

```
[ ]  Read this whole file once. Do not skip section 7.
[ ]  Confirm the 2-message budget is fresh (no Fable-5 messages in the
     last 5 hours). If you have 1 left, abort — you cannot recover.
[ ]  Run scripts/build_fable5_prompt.py to build /tmp/fable5_prompt1.txt
[ ]  Skim /tmp/fable5_prompt1.txt. Verify:
     - <file_index> includes every MUST_INCLUDE file you care about
     - no secret leaked (search for API_KEY, TOKEN, PASSWORD, SECRET)
     - size is 40–80 KB; smaller means the heuristic missed files
[ ]  Manually prepend <project_context> and <prior_review_summary>
     blocks at the top of the user message
[ ]  Open Fable-5 chat. Paste system block (section 3.1) as system.
     Paste user block as the single user message.
[ ]  Wait for full reply. Copy it to /tmp/fable5_reply1.md
[ ]  Build Prompt 2 manually (section 4.2), substituting
     <prior_review_status> with Fable-5's reply and <prior_roadmap>
     with the relevant phase-plan slice.
[ ]  Send Prompt 2 (this is your SECOND message — the budget is now 0).
[ ]  Copy the reply to /tmp/fable5_reply2.md.
[ ]  Move both replies into docs/12_claude_review/ as
     fable5-review-2026-MM-DD-reply1.md and ...-reply2.md.
[ ]  Open a follow-up Agent Zero session and process the recommendations
     into docs/13_review_response/, mirroring the 2026-05-18 workflow.
```

---

## 7. What Fable-5 does **not** see

Be explicit with the user (in your response that closes this Agent Zero
task) about these blindspots. If you do not, Fable-5 will produce a
review that is technically correct but practically unusable.

1. **Runtime state.** No process listings, no live logs, no `ps`, no
   curl traces, no test-runner output. Fable-5 cannot observe
   behaviour — only structure. If you want behavioural findings, paste
   the relevant log slice or pytest -v output.
2. **The git log.** It cannot see commit history, branches, or PRs.
   If a finding depends on "this was fixed in commit X", quote the
   diff into `<relevant_files>` yourself.
3. **en-croissant upstream changes.** `apps/desktop/` is a fork;
   Fable-5 sees it as a directory, not as something with an upstream.
   Boundary leaks between the fork and the project must be inferred
   from `docs/14_adrs/ADR-0004-license-posture.md` and `.upstream-ref`.
4. **Cost / latency numbers.** No real-world OpenRouter bill, no
   engine-pool timings, no live Redis memory pressure. Only what you
   paste.
5. **The LLM router model switch.** As of 2026-07-07 the primary is
   `z-ai/glm-5.2` (reasoning model) and the router was patched to
   fall back to the `reasoning` field. Mention this in the
   <project_context> block — otherwise Fable-5 may flag the empty
   `content` response as a bug rather than the expected reasoning
   pattern.
6. **The desktop-fork coupling.** Tauri + the en-croissant React UI
   share state through `apps/desktop/src/state/`. If you omit those
   files, Fable-5 will under-rate the integration-surface risk.
7. **The 2026-06-18 false-claims incident.** A previous automated
   memory-memorize run fabricated facts that landed in the response
   doc. The fix (`memory_memorize_enabled: false`) is in
   `default_config.yaml`. Fable-5 may want to verify it.

---

## 8. Open questions for v2

Things this v1 draft does **not** solve — record these in the review
session so they get answered before the next iteration:

- **Embedder-based ranking.** Section 5.1 uses a TF-IDF-ish keyword
  heuristic. A sentence-transformer ranker (already a dev dep) would
  improve recall on semantic questions ("JWT" vs "token"). Worth a
  one-hour spike.
- **Token-budget math.** 80 KB cap is a guess. Should be tuned against
  the specific Fable-5 context window (find out — likely 128k–200k
  tokens). Currently we waste capacity by being conservative.
- **Two-pass design.** Option C from fable.txt (single Fable-5 message
  doing both recon + answer) was rejected as too unreliable. Worth
  revisiting once we know the real Fable-5 quality.
- **Prompt caching.** Option D from fable.txt only matters once we
  move to PAYG. Document but do not implement now.
- **Versioning of this file.** Should be regenerated per audit
  topic, not reused across topics. The MUST_INCLUDE list is the
  per-topic knob.
- **Where do the Fable-5 replies live?** Plan: `docs/12_claude_review/`
  with date prefix, mirroring the existing claude-review pattern.
  Update section 6 checklist accordingly.

---

*End of v1 draft. Once this is committed, the next Agent Zero session
opens the actual Fable-5 chat, runs the checklist, and writes the
replies to `docs/12_claude_review/fable5-review-2026-MM-DD-reply{1,2}.md`.*
