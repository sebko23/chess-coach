# gui-verify — record of TypeScript compile failures found

**Author:** Hermes session 2026-08-01
**Branch:** `gui-verify`
**Status:** This BBF found a **real breakage** introduced by the fix-pnpm-vulns BBF
(commit `095115f`). The follow-up is a code-fix BBF; this BBF is the record.

## Summary

The `fix-pnpm-vulns` BBF (commit `095115f`) bumped `react-mosaic-component`
from `^6.1.1` to `^7.0.0` (a major version bump) to fix the uuid
override propagation. The PR description flagged this as a real
risk: "Could break the GUI; follow-up BBF should verify dev-mode boot."

This BBF ran the same TypeScript compile check the CI uses
(`pnpm tsgo --noEmit`, but invoked directly via `node_modules/.bin/tsgo.cmd`
to avoid the `pnpm install` hang documented in BUILDING.md footgun #4).

**Result: 4 distinct breakage sites in 3 files.** The major version
bump broke the GUI as predicted. The fix is a code-fix BBF (separate).

## The 4 breakage sites

### Site 1: `src/components/common/EvalChart.tsx:235, 288`

```
error TS2322: Type 'TooltipPayload' is not assignable to type 'readonly { payload: DataPoint; }[]'.
  Type 'TooltipPayloadEntry' is not assignable to type '{ payload: DataPoint; }'.
    Property 'payload' is optional in type 'Payload<ValueType, NameType>' but required in type '{ payload: DataPoint; }'.
```

**Cause:** Recharts 2.x → 3.x type signature change. The `TooltipPayload` type now has `payload` as **optional**, but the project's type annotation declares it as required. This is **a Recharts update that came along with the major version bump chain** (Recharts 3.x is a transitive of @mantine/charts 8.3.14).

### Site 2: `src/components/home/PersonalCardPanels/RatingsPanel.tsx:191`

```
error TS2769: No overload matches this call.
  The last overload gave the following error.
    Argument of type 'ReactNode' is not assignable to parameter of type 'string | number'.
      Type 'undefined' is not assignable to type 'string | number'.
```

**Cause:** Same Recharts 3.x type signature tightening. A `<text>` or `<label>` prop now rejects `ReactNode` (only `string | number` accepted).

### Site 3: `src/components/tabs/BoardsPage.tsx:282`

```
error TS2353: Object literal may only specify known properties, and 'first' does not exist in type 'MosaicSplitNode<ViewId> | MosaicTabsNode<ViewId>'.
```

**Cause:** **`react-mosaic-component@7.x` API change.** The `MosaicSplitNode`/`MosaicTabsNode` discriminated union no longer has a `first` property. The project's code uses `first` to access the first child of a split node.

### Site 4: `src/components/tabs/BoardsPage.tsx:311, 322, 338`

```
error TS2769: No overload matches this call.
  The last overload gave the following error.
    Type 'ReactNode' is not assignable to type 'ReactElement<unknown, string | JSXElementConstructor<any>>'.
      Type 'undefined' is not assignable to type 'ReactElement<unknown, string | JSXElementConstructor<any>>'.
```

**Cause:** Same react-mosaic-component@7.x type signature tightening. `ReactNode` not assignable to `ReactElement` (children must be a ReactElement, not arbitrary ReactNode like strings or null).

## Verifications NOT broken

- **`pnpm audit --audit-level moderate --prod`:** PASS (no prod vulns)
- **`pnpm lint` (oxlint):** PASS (79 warnings, 0 errors; warnings are pre-existing react-hooks deps)
- **`uv sync --frozen`:** PASS (lockfile is reproducible)
- **Backend Python lib imports (`chess_coach.storage`, `chess_coach.protocol_types`):** PASS (no module-level errors from the new uv.lock)

The breakage is **TypeScript-only** in 3 specific files, not a global build failure.

## Suggested fix shape (for the follow-up BBF)

The fixes are mechanical:

1. **`EvalChart.tsx:235, 288`:** change `payload: DataPoint` type annotations to `payload?: DataPoint` (optional), and add null guards where the value is dereferenced. This is the Recharts 3.x type change.

2. **`RatingsPanel.tsx:191`:** this is a separate Recharts 3.x type tightening on `labelFormatter` (or similar prop). The fix is to widen the callback parameter type, cast to `string`, or assert non-undefined. It is NOT the same fix as site 1 — site 1 is about the `payload` field being optional, site 2 is about the callback's parameter type rejecting `ReactNode`.

3. **`BoardsPage.tsx:282`:** the `MosaicSplitNode` API changed. Per the 7.x type definitions (`node_modules/react-mosaic-component/types-*.d.ts`), the 7.x shape requires `type: 'split'` (discriminator) + `children: MosaicNode<T>[]` (array, not the `first`/`second` named properties of the legacy `LegacyMosaicParent` which is now deprecated). The fix is to migrate from the named-property shape to the discriminator-union shape. See the type definitions for the exact replacement.

4. **`BoardsPage.tsx:311, 322, 338`:** cast children to `ReactElement` or wrap in a `<>` fragment explicitly. The 7.x types are stricter (`ReactNode` not assignable to `ReactElement`).

Estimated scope: ~50-100 LOC of code changes across 3 files. ~1 hour of focused work. New BBF needed.

## Cross-references

- `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-08-01-fix-pnpm-vulns.md` (the original fix-pnpm-vulns report; the major-version-bump risk is documented in §"Honest disclosures")
- `BUILDING.md` `### pnpm dep upgrade workflow (BBF-fix-pnpm-vulns)` footgun #4 (pnpm install hangs in sandbox — relevant to this BBF because we used `--lockfile-only` + direct binary invocation to work around it)
- `apps/desktop/package.json:79` (the `react-mosaic-component: ^7.0.0` direct dep)
- `apps/desktop/src/components/tabs/BoardsPage.tsx:282, 311, 322, 338` (the 4 breakage sites)
- `apps/desktop/src/components/common/EvalChart.tsx:235, 288` (the Recharts breakage)
- `apps/desktop/src/components/home/PersonalCardPanels/RatingsPanel.tsx:191` (the Recharts breakage)

## Verification methodology

The TypeScript compile check was run via:

```bash
cd apps/desktop
node_modules/.bin/tsgo.cmd --noEmit
```

This was the most reliable way to invoke tsgo in the sandbox because:
- `pnpm tsgo --noEmit` (the package.json script) timed out at 3 minutes (BUILDING.md footgun #4)
- `pnpm install --lockfile-only` completed in 1.3 seconds (the workaround)
- `node_modules/.bin/tsgo.cmd --noEmit` invoked tsgo directly and completed in 26.8 seconds with the 4-error output above

The lint check was run via:

```bash
cd apps/desktop
node_modules/.bin/oxlint.cmd
```

This completed in 6.8 seconds with 79 warnings, 0 errors. (The warnings are pre-existing react-hooks exhaustive-deps issues, not from the major version bump.)

## Out of scope

- The actual code fixes (separate follow-up BBF).
- Verifying the production build (`pnpm tauri build` with bundling) — deferred.
- Visual inspection of the GUI in a real browser — manual, deferred.
- Verifying the Tauri runtime in dev mode (`pnpm tauri dev`) — deferred (requires backend + WebView).
