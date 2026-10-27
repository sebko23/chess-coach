# BBF-gitleaks-stale-docs-ledger — reconcile the stale `targetRules` documentation

**Sprint intent:** Documentation/ledger only. Reconcile the statements left stale by
PR #184 (the merged one-line `.gitleaks.toml` config BBF) and record the newly
measured gitleaks 8.30.1 target-rule scoping behavior in the established ledger
structure.

**Base:** `main @ a5bd6d38213352e9886700c076a9fb481d0dec57` (the PR #184 merge
commit).

---

## §1. Why this exists

PR #184 removed the obsolete `lichess-pat` target-rule ID from `.gitleaks.toml`.
It deliberately changed only that one line, so the documentation that described the
pre-#184 four-ID list was left saying things that were no longer true.

Three current-state statements were stale:

| Site | Stale claim |
|---|---|
| `.gitleaks.toml` (comment above `[allowlist]`) | "The `lichess-pat` and `github-pat` rules are listed defensively" — `lichess-pat` is no longer in the list at all, and the framing ("defensively") misdescribes the retained ids |
| `OPEN-FOLLOWUPS.md` FU-38 lead block | presented the four-ID list as the config's contents |
| `OPEN-FOLLOWUPS.md` FU-38 "The fix" block | presented the four-ID list as the shipped `targetRules` |
| `OPEN-FOLLOWUPS.md` FU-38 flip-13 correction block | said the list "still names `lichess-pat`" and that the follow-up BBF was "deliberately NOT discharged here" |

The PR #184 body and the FU-38 `## Resolved` entry also record the scoping
behavior; that behavior was not written down in the ledger.

---

## §2. Scope

Three files, three kinds of change:

1. **`.gitleaks.toml`** — the explanatory comment above the `[allowlist]` table
   only. The functional `targetRules` value, the 13 `paths` entries, the `[extend]`
   block, and the allowlist `description` are byte-identical to the merged tree.
2. **`docs/16_audit/OPEN-FOLLOWUPS.md`** — three current-state quotations
   reconciled, the FU-38 `## Resolved` historical paragraph labelled as the
   pre-PR-#184 state, and a new FU-48 entry added.
3. **`docs/16_audit/BBF-gitleaks-stale-docs-ledger.md`** — this brief.

**Not touched:** the functional rule list; any CI workflow file; any action version;
any detector; any allowlist path; any scanner configuration; FU-35; FU-20.

---

## §3. The measured behavior being recorded

Corpus: a fresh full clone of `origin/main` at `a5bd6d38` (449 commits reachable,
432 scanned by gitleaks). Every run used `--redact`, so no report carried a secret
value.

| gitleaks | `targetRules` configuration | findings |
|---|---|---|
| 8.24.2 | all three retained | 2 |
| 8.24.2 | minus `generic-api-key` | 2 |
| 8.24.2 | minus `github-pat` | 2 |
| 8.24.2 | minus `curl-auth-header` | 2 |
| 8.24.2 | empty (`[]`) | 2 |
| 8.24.3 | all three retained | 2 |
| 8.24.3 | minus `generic-api-key` | 2 |
| 8.24.3 | minus `github-pat` | 2 |
| 8.24.3 | minus `curl-auth-header` | 2 |
| 8.24.3 | empty (`[]`) | 2 |
| 8.30.1 | all three retained | 2 |
| 8.30.1 | minus `generic-api-key` | 6 |
| 8.30.1 | minus `github-pat` | 2 |
| 8.30.1 | minus `curl-auth-header` | 27 |
| 8.30.1 | empty (`[]`) | 2 |

Control: the `[allowlist]` table removed with `[extend] useDefault = true` kept
reports **31 findings on all three versions**, confirming the allowlist is still
effective and that the 2-finding rows are not an artifact of a config that stopped
suppressing anything.

### What each row establishes

1. **On 8.30.1, path allowlisting is scoped to `targetRules`.** Dropping
   `generic-api-key` raises 2 → 6 (the 4 extra are the log-redaction fixtures and
   the 2 keybinding strings); dropping `curl-auth-header` raises 2 → 27 (25
   dev-fixture `curl-auth-header` matches plus the 2 `generic-api-key` residual).
   The same removals leave 8.24.x at 2.
2. **The three retained ids are load-bearing on 8.30.1.** `generic-api-key` and
   `curl-auth-header` are load-bearing directly by the counts above. `github-pat`
   matches zero findings against this corpus, so dropping it changes no count here;
   it was proven load-bearing in principle by inserting a high-entropy synthetic
   `ghp_` token into an allowlisted path in a scratch clone — with `github-pat` in
   `targetRules` the count stayed at 2, with it removed the count rose to 3 with a
   `github-pat` finding. The same probe left 8.24.2 and 8.24.3 at 2 either way. The
   probe commit was discarded and the scratch clone reset to the pristine landed
   tree before this brief was written; no synthetic value appears in any tracked
   file, diff, or report.
3. **An empty `targetRules` is NOT equivalent to a partial list.** Empty yields 2
   findings on all three versions — the same count as the full three-id list — while
   a partial list can yield 6 or 27 on 8.30.1. Emptiness is indistinguishable from
   the full list by count alone, but a partial list is strictly worse than either.
4. **Future rule-list changes require cross-version re-measurement.** A count
   measured on 8.24.x does not transfer to 8.30.1.

---

## §4. Two corrections to the directive's framing

The directive's required content says "Removing `github-pat` or `generic-api-key`
can expand the 8.30.1 finding set" and "An empty `targetRules` list is not
equivalent to a partial list". Both were re-measured against the landed tree, and
the ledger records the measured behavior with the precision the measurement
supports:

- **`github-pat`:** against this corpus it expands nothing (2 findings either way),
  because it matches zero findings. It is nonetheless load-bearing on 8.30.1, proven
  by the synthetic-token probe above. The ledger says both things rather than
  claiming a count expansion that was not measured.
- **Empty vs partial:** empty (`[]`) and the full three-id list both give 2
  findings on 8.30.1; a partial list gives 6 or 27. The divergence is between
  *partial* and *both empty and full* — not between empty and partial. The ledger
  states this as measured, with the table as the evidence.

---

## §5. Verification performed

- `.gitleaks.toml` parses as valid TOML; `targetRules` is exactly the three
  authorized ids; `paths` is still 13 entries; `extend.useDefault` is still `true`;
  the allowlist `description` is unchanged.
- The `.gitleaks.toml` diff touches only comment lines — the functional lines are
  byte-identical to the merged tree.
- `git diff --check` clean.
- `scripts/dev/verify_commit_refs.py` and `scripts/dev/verify_bbf_flip_rules.py`
  both exit 0 against the final commit body AND the final PR body.
- Every cited SHA resolves as an existing ancestor of `main`.
- A bounded gitleaks scan confirms no credential or historical token value in the
  diff, commit body, PR body, or scratch files.

---

## §6. Cross-references

- PR #184 — the merged one-line config BBF (merge commit `a5bd6d38`).
- FU-38 — the allowlist fix and the accepted 2-finding residual risk.
- `.gitleaks.toml` — the corrected explanatory comment.
