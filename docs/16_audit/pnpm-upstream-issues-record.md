# pnpm upstream issues — record of comments posted

**Author:** Hermes session 2026-08-01
**Branch:** `pnpm-upstream-issues` (this doc was created on this branch; the substantive work is upstream on the pnpm repo).

## Summary

The `fix-pnpm-vulns` BBF (commit `095115f`) discovered 5 pnpm footguns
that required brute-force `rm pnpm-lock.yaml` operations. Per
the external developer's Path A directive, the upstream pnpm
issues for these footguns should be filed.

**Approach:** comment on existing open issues, not file duplicates.
All 3 footgun patterns are already reported as open issues. Filing
duplicates would be noise; commenting on the existing issues with
the 2026 reproduction is more useful.

## The 3 comments posted

| Footgun | Existing issue | Comment URL | Action |
|---|---|---|---|
| #1: `--lockfile-only` silently skips overrides | [#6094](https://github.com/pnpm/pnpm/issues/6094) (open 2.5 yrs) | [comment 5152326477](https://github.com/pnpm/pnpm/issues/6094#issuecomment-5152326477) | 2026 reproduction; suggested warning. |
| #1+#2: Override matched no dep / silent skip | [#12741](https://github.com/pnpm/pnpm/pull/12741) (open feature req) | [comment 5152326566](https://github.com/pnpm/pnpm/pull/12741#issuecomment-5152326566) | Strong endorsement; concrete example of the 2-hour debugging cost. |
| #3: Overrides blocked by exact-pinned transitive | [#6774](https://github.com/pnpm/pnpm/issues/6774) (open 3 yrs) | [comment 5152326626](https://github.com/pnpm/pnpm/issues/6774#issuecomment-5152326626) | Exact 2026 reproduction (uuid@9.0.1 blocked by `react-mosaic-component@6.x` exact-pin); workaround; suggested discriminator. |

## Footguns NOT filed (with reasons)

- **Footgun #2: pnpm.overrides doesn't override direct deps with stricter version ranges** — pnpm design, not a bug. `^8.0.0` ⊇ `^8.0.16` makes the override moot by definition. Documented in BUILDING.md; no upstream report needed.
- **Footgun #4: pnpm install (full) hangs in sandbox environments** — environmental, not pnpm's bug.
- **Footgun #5: pnpm 11 requires Node 22.13+** — already documented in pnpm's Node compatibility matrix at https://r.pnpm.io/comp.

## Cross-references

- `docs/08_security/security-strategy.md` — the security strategy doc.
- `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-08-01-fix-pnpm-vulns.md` — the full fix-pnpm-vulns issue report.
- `BUILDING.md` `### pnpm dep upgrade workflow (BBF-fix-pnpm-vulns)` — the BUILDING.md section that documents all 5 footguns.

## Out of scope

- Filing new issues if the existing ones get closed without resolution.
- Following up with the pnpm maintainers.
- Cross-posting to the pnpm Slack or Discord.
