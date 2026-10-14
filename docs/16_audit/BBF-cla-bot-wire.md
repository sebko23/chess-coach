# BBF-cla-bot-wire — wire CLA-bot / cla-assistant.io as a Backend merge gate

**Sprint intent:** wire the `cla-assistant.io` GitHub App onto
`sebko23/chess-coach` so every PR that touches the Backend codebase
(`services/chess_coach/**`) is gated on a signed CLA. The App
itself posts the merge-gate check; this BBF's in-repo work is
the brief + a `CONTRIBUTING.md` link update.

**Root cause / context:**

- `docs/10_roadmap/phase-plan-v2.md:247` (Phase 1 additional exit
  criteria): "CLA-bot or `cla-assistant.io` wired into CI as a
  hard merge gate for the Backend codebase."
- `CLA-ICLA.md` (Apache ASF ICLA template, P1 binding
  architectural requirement per `docs/13_review_response/legal-opinion-integration.md`
  §C.1) and `CLA-CCLA.md` (corporate variant) are already in
  the repo root. The TEMPLATE status header in `CLA-ICLA.md:3`
  notes these are placeholders pending counsel review; the
  *signing flow* itself can be wired before counsel review, but
  the App installation is the project owner's action, not a
  code change.
- `CONTRIBUTING.md` currently has a "Submitting a Pull Request"
  section (lines 32-48) with no CLA mention. Contributors opening
  a PR today have no signal that a CLA signature will be required
  at the new merge gate.
- The `cla-assistant.io` App (SAP-hosted, free for OSS) is the
  canonical recipe: it comments on each opened PR, posts a status
  check named "CLA", and fails the check until the contributor
  signs the CLA via the App's PR comment UI. The App's check is
  the merge gate; no custom in-repo CI job is required.

**Scope (in-repo, this BBF):**

- `docs/16_audit/BBF-cla-bot-wire.md` — this brief (creates a
  tracked record per the v0.7.92 lost-briefs incident convention
  that briefs live at `docs/16_audit/BBF-*.md`).
- `CONTRIBUTING.md` — add a "Contributor License Agreement" section
  in the "Submitting a Pull Request" flow that points contributors
  at the CLA-signing UI on first PR. This is the only in-repo
  contributor-visible change.

**Scope (out-of-repo, project-owner action, deferred):**

1. Sebastian installs the `cla-assistant` GitHub App on the
   `sebko23/chess-coach` repo. The App is free for OSS use.
   Installation requires org-owner / repo-admin privileges
   (outside the agent's tool scope).
2. Sebastian creates two public GitHub Gists:
   - `cla-individual.md` — content of `CLA-ICLA.md` (after the
     counsel-reviewed final version is committed).
   - `cla-corporate.md` — content of `CLA-CCLA.md` (same).
3. Sebastian links the Gists to the `sebko23` org via the
   `cla-assistant.io` web UI.
4. Sebastian configures the path filter in the App settings to
   match `services/chess_coach/**` (the Backend codebase). PRs that
   touch only frontend / docs / CI do NOT trigger the gate.

**Scope (out of scope, NOT this BBF):**

- A custom in-repo CI check for CLA. The App's own check is the
  gate. Adding a second in-repo check would race with the App's
  check and produce noise. The App's check is also the merge
  gate in the GitHub UI's "branch protection" settings; a
  custom in-repo check would require manual branch-protection
  configuration that the App handles automatically.
- The counsel review of `CLA-ICLA.md` / `CLA-CCLA.md`. The
  placeholders in those files are P1 (per the legal-opinion
  binding architectural requirement). Until counsel review
  ships, the Gists linked to the App point at the
  placeholder text. The signing flow works regardless of the
  text content; the text is what counsel is reviewing.
- A `GITHUB_ADMIN_USERS` configuration in the App. The
  `cla-assistant.io` App has a separate config for which users
  can administer the org's CLA settings. Out of scope; default
  (any org owner) is fine for now.

**Precise edits (in-repo, this BBF):**

1. **`CONTRIBUTING.md` insertion** at the start of the
   "Submitting a Pull Request" section (currently line 32):

   ```markdown
   ## Contributor License Agreement (CLA)

   Before your pull request can be merged, you must sign the
   CHESS COACH CLA. We use the [cla-assistant](https://cla-assistant.io)
   bot to track signatures:

   - The bot comments on every opened PR with a one-click link to
     sign the CLA (individual or corporate variant).
   - Once you sign, the bot updates the PR's CLA status check to
     "success" and your PR is eligible to merge.
   - The CLA check fires only for PRs that touch the Backend
     codebase (`services/chess_coach/**`). Frontend-only and
     docs-only PRs are not gated.

   The CLA text is at [`CLA-ICLA.md`](./CLA-ICLA.md) (individual)
   and [`CLA-CCLA.md`](./CLA-CCLA.md) (corporate). Both are
   derived from the Apache Software Foundation CLA template,
   adapted for the chess-coach project's binding architectural
   requirements (see
   `docs/13_review_response/legal-opinion-integration.md` §C.1).

   **Status (BBF-cla-bot-wire):** the `cla-assistant` GitHub App
   must be installed on `sebko23/chess-coach` by the repo owner
   before the gate takes effect. Until the App is installed, the
   CONTRIBUTING.md link update is informational; PRs do not
   actually fail the CLA check.

   ## Submitting a Pull Request

   1. Fork the repo
   ...
   ```

   The "Submitting a Pull Request" section's existing 1-7 list
   remains unchanged.

**Verification protocol (post-merge, project owner does these):**

- V1: Visit `https://github.com/sebko23/chess-coach/settings/installations`
  (requires org owner). Verify the `cla-assistant` App is
  installed on the repo.
- V2: Visit `https://cla-assistant.io/` and sign in with the
  `sebko23` GitHub account. Verify the two Gists
  (`cla-individual.md`, `cla-corporate.md`) are listed and
  linked to the `sebko23/chess-coach` repo.
- V3: In the App's repo settings, verify the path filter is set
  to `services/chess_coach/**` (the Backend codebase).
- V4: Open a test PR that touches `services/chess_coach/gateway/`
  with a non-owner GitHub account. Verify the App posts a "Please
  sign the CLA" comment on the PR and the CLA status check is
  "failure" until the contributor signs.
- V5: After signing, verify the CLA status check transitions to
  "success" and the PR is eligible to merge.
- V6: Open a test PR that touches ONLY `apps/desktop/` (frontend).
  Verify the App does NOT comment and the CLA status check is
  not posted (path filter working).

**Out of scope (explicit):**

- Branch-protection rule changes. The `cla-assistant` App's
  check is the merge gate in the branch-protection rule; no
  change to the existing `main` branch protection rule is
  required by this BBF.
- Backend test-enforcement (FU-28) wiring. Out of scope; the
  `cla` check is orthogonal to the test glob.
- The `pnpm-workspace.yaml` / `pnpm.overrides` block (FU-34 +
  FU-37). Out of scope; pnpm advisories are FU-37 (v1.x
  deferral).

**Final report format:** the squash-merge commit body documents
this BBF's two-file diff (1 brief + 1 CONTRIBUTING.md section
insert) + the deferred project-owner action items 1-4.

**Hermes verification (re-derive, post-merge):**

- `git log -1 --format=%B HEAD` on `main` shows the squash
  commit body documents the deferred items explicitly.
- `git show main:CONTRIBUTING.md | grep -A 2 "Contributor
  License Agreement"` returns the new section header.
- `git show main:docs/16_audit/BBF-cla-bot-wire.md | head -5`
  returns the brief's "Sprint intent" paragraph.
- The repo does NOT have a custom CLA CI job in
  `.github/workflows/` (the App's check is the gate; no
  duplicate).