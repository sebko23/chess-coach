# Public Specifications

This directory hosts the **public, third-party-implementable** specifications that define how CHESS COACH components interoperate.

## Why a separate `specs/` tree

The protocol that the GUI and Backend speak is licensed CC-BY-4.0 — independently of the GPL-3.0 GUI and the Apache-2.0 Backend. Keeping the spec in its own tree with its own license file makes the boundary observable. This is binding architectural commitment **P3** (see `docs/13_review_response/legal-opinion-integration.md` §C.2) and the legal foundation of the project's separate-works license posture under GPL-3.0-only §5 (see `docs/13_review_response/legal-protocol-assessment-received.md`).

## Layout

| Path | Contents |
|---|---|
| `v1.0/` | Protocol version 1.0.0 (stable). |
| `v1.0/chess-coach-protocol-v1.md` | The specification document. CC-BY-4.0. |
| `v1.0/schemas/` | JSON Schemas for every request and response shape. CC-BY-4.0. |
| `v1.0/tests/` | Conformance test vectors and runner. MIT (test code is generally useful outside this project). |

## Versioning

Semantic versioning (see `v1.0/chess-coach-protocol-v1.md` §9). New major versions get their own directory (e.g. `v2.0/`); minor and patch updates amend the existing directory and update the `CHANGELOG` within it.

Major versions can coexist: a backend may serve `/v1/...` and `/v2/...` simultaneously.

## Third-party implementations

The protocol is designed so that any party can publish a conforming GUI or Backend in any language, under any license they choose. We welcome reference implementations and will link to community ones from this directory's README once they exist.
