# ADR-0005: Coach panel state uses Jotai

**Status:** Accepted
**Date:** 2026-05-18

## Decision

Coach panel state (`src/state/atoms/coach/`) uses Jotai to match en-croissant's
existing atom-based architecture. The original architecture document referenced
Zustand as a candidate; Jotai was already present and in active use in the
upstream codebase, making it the correct choice for consistency.

## Consequences

All coach state is expressed as Jotai atoms. Future coach modules follow the
same pattern. No Zustand dependency is introduced.
