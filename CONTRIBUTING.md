# Contributing to CHESS COACH

CHESS COACH is a Python FastAPI backend plus a Tauri/React desktop GUI
forked from [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant).
Backend and frontend are independent licensing units (see `LICENSING.md`),
and contributions to one do not affect the other.

## Where to start

- **Issues**: see the GitHub issues page. The maintainers tag work by
  sprint ID (BBF-N). BBF-18 through BBF-26 are the recent perf-scaling
  and GUI work; BBF-27 onwards is the repo-readiness push.
- **Discord**: there's a chess-coach channel linked from the repo's
  social page.
- **Sprint history**: `docs/CHANGELOG.md` lists every BBF with its
  scope, commit, and what was verified.

## Development workflow

The repo has two runtimes. You'll need both set up:

- **Backend**: Python 3.11+, `uv` recommended. See `BUILDING.md` §
  "Building the backend" for the full setup, including the
  `CHESS_COACH_DATA_DIR` and `CHESS_COACH_BACKEND_TOKEN` env vars.
- **Frontend**: Node 20+, pnpm 9+, Rust (for Tauri shell). See
  `BUILDING.md` § "Building the desktop GUI".

If you're new to the project, the first thing to do is `BUILDING.md`
end-to-end. Run the smoke test in `tests/integration/smoke_test.py` to
confirm the full lazy path works on your machine.

## Submitting a Pull Request

1. Fork the repo
2. Clone your fork: `git clone git@github.com:{you}/chess-coach.git`
3. Create a branch off `main`: `git checkout -b bbf-N-short-slug`
4. Make your changes
5. Run the verification:
   - Backend: `python tests/integration/smoke_test.py` (with the
     backend running)
   - Frontend: `cd apps/desktop && pnpm exec tsgo --noEmit`
6. Commit with a message that follows the existing `BBF-N:` prefix
   style
7. Open a PR

The maintainers review PRs sprint-by-sprint. A PR that touches a
large file (1000+ lines) without an explicit brief is likely to
be closed and redirected to a planning thread.

## Frontend fork: pulling upstream en-croissant

`apps/desktop/` is a fork of [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant)
(commit SHA stored in `.upstream-ref`). When upstream en-croissant
makes a change you want to pull in:

```bash
# Add en-croissant as a remote (once)
git remote add encroissant https://github.com/franciscoBSalgueiro/en-croissant.git

# Fetch the upstream tip
git fetch encroissant

# Merge upstream's main into our apps/desktop subtree.
# The apps/desktop directory is the only place we touch en-croissant code;
# other directories are original chess-coach work.
git merge encroissant/main --allow-unrelated-histories \
    -X subtree --into=apps/desktop
# Resolve conflicts in apps/desktop/. Prefer our chess-coach-specific
# changes (GamesPage.tsx, GameDetailPage.tsx, bindings, etc.) over upstream.
```

The current upstream commit we forked from is recorded in
`.upstream-ref` at the repo root. This is the SHA we last merged or
diverged from. If you want to know what changes happened in
en-croissant since our last merge, compare
`en-croissant/main` to the SHA in `.upstream-ref`:

```bash
git log --oneline $(cat .upstream-ref)..encroissant/main -- apps/desktop
```

When you do pull upstream, update `.upstream-ref` to the new SHA:

```bash
ENCROISSANT_SHA=$(git rev-parse encroissant/main)
echo "$ENCROISSANT_SHA" > .upstream-ref
git add .upstream-ref
git commit -m "chore: update .upstream-ref after en-croissant merge"
```

## Backend sprint workflow

Sprints are BBF-N, planned in a brief (1-2 pages) and approved before
coding starts. A good brief has:

1. **Sprint intent** — one paragraph, no rationale, just what's being built.
2. **Root cause / context** — for closing-bug sprints, the verified file
   paths and line numbers. For new-feature sprints, the verified
   ground truth.
3. **Scope** — required files, out-of-scope files, decisions baked in.
4. **Precise edits** — exact hunks to apply, with surrounding context
   lines for uniqueness.
5. **Verification protocol** — numbered V1..VN bash commands.
6. **Out of scope** (optional) — explicit list of what NOT to touch.
7. **Final report format** — exact template the subagent fills in.
8. **Hermes verification** — what the supervising agent will re-derive.

Briefs that tell the implementer to "investigate and decide" lead to
scope drift. Bake decisions in the brief; expect implementers to
apply them literally.

## Conventions

- **Commit messages**: `<type>(<scope>): BBF-N <one-line summary>` where
  type is one of `feat`, `fix`, `refactor`, `docs`, `test`, `chore`,
  and scope is the affected module (`gui`, `import`, `gateway`, etc.).
  Body explains the why and the verification.
- **Pre-commit hook**: every commit runs `lint-utf8.mjs` to catch
  mojibake. Don't bypass it.
- **No `--force` push to `main`**. If you need to rewrite history,
  coordinate in the PR.
- **No secrets in commits**. The `secrets-handling` skill and the
  `.gitignore` cover this. If you accidentally committed a secret,
  rotate it BEFORE merging.

## Testing

The repo currently has no automated test suite. BBF-30 (in progress)
will add GitHub Actions CI running the smoke test. Until then, manual
verification via `tests/integration/smoke_test.py` is the gate.

## Support

Open an issue or contact the maintainers via the channels listed on
the repo's social page.
