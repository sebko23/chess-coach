# Architecture Decision Records (ADRs)

This directory captures **point-in-time decisions** about CHESS COACH architecture, in the lightweight Michael Nygard format. Each ADR has a number, a status, a context, a decision, and consequences.

## When to write an ADR

- A non-obvious architectural decision is being made (or a default is being chosen over an alternative).
- A binding architectural rule is being added or changed.
- The license posture of any workspace changes.
- A new external service dependency is being introduced.
- A previously-rejected option becomes viable and is being reconsidered.

## When NOT to write an ADR

- Routine implementation choices entirely within one module that don't touch interfaces.
- Reversible config-level decisions.
- Doc-only changes.

## Format

Copy `ADR-0000-template.md` to `ADR-NNNN-short-slug.md` and fill it in. Number is monotonic — never reuse. Status moves through `proposed → accepted → (deprecated | superseded by ADR-MMMM)`.

## Index

| # | Title | Status |
|---|---|---|
| 0000 | Template | n/a |
| 0001 | Async/sync boundary in backend services | accepted |
| 0002 | Error envelope and error-code allocation | accepted |
| 0003 | Schema evolution (SQLite migrations + Pydantic versioning) | accepted |
| 0004 | License posture per workspace | accepted |
