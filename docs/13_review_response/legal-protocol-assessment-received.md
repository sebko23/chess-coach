# Protocol Contract Assessment — Received from OSS Counsel (2026-05-18)

**Re**: `docs/16_protocol/chess-coach-protocol-v1.md` (then v1.0.0-draft.1)
**Pursuant to**: Closing observation #3 of prior analysis; cover note in §F of the integration document
**Outcome**: U1 fully resolved subject to (a) P1+P2+P3 adoption (already binding in the package) and (b) R1 + R2 applied to the protocol spec before v1.0.0 publication.

**R1 and R2 have been applied. Protocol is now published as v1.0.0 stable** — see §16 changelog of `chess-coach-protocol-v1.md`.

---

## Counsel's verdict, verbatim

### (a) Does this protocol support the aggregate / separate-works position?

> **Yes — and it does so more strongly than the prior analysis could assume.**
>
> The prior analysis characterised Q1 as "plausibly no, with meaningful residual risk." Having reviewed the protocol contract, I am prepared to upgrade that to:
>
> **Plausibly no, with low residual risk, conditional on one targeted revision (see §c below).**
>
> Here is the basis for that upgrade, clause by clause against the FSF's two-part test (mechanism + semantics):

**Mechanism of communication.** Counsel found: "HTTP/1.1 REST and WebSocket over TCP on the loopback interface — the canonical 'separate programs communicating via sockets' pattern that the FSF FAQ identifies as the paradigm case for separate programs. There is no shared memory, no FFI, no dynamic linking, no shared object code, and no named pipe. The protocol explicitly prohibits co-process control surfaces and §1.5 states that neither side is privileged in the lifecycle of the other. The mechanism is as clean as it is possible to be."

**Semantics of communication.** Counsel found that the data exchanged (FEN, UCI, centipawns, PGN, ISO-8601 timestamps, UUIDs, HTTP status codes, narration text, generic job envelopes) are all standard, publicly documented types — not the "complex internal data structures" the FSF FAQ warns about. The grounded-narration metadata structure is the most complex payload but is "a well-defined validation metadata envelope" interpretable from spec alone. Verdict: "The semantics of communication are the **opposite of 'intimate.'** They are generic, standard, and fully specified in a public document. The FSF FAQ's concern about 'exchanging complex internal data structures' does not apply here."

**Independence of both sides.** Counsel found the protocol "affirmatively establishes independence in both directions" — Backend runs standalone via CLI; spec is CC-BY-4.0; third-party implementations of either side explicitly invited. "These are not boilerplate statements — they are structural design choices that are observable and verifiable. A court or the FSF reviewing this protocol would find it difficult to characterise the Backend as 'by its nature an extension of' the GPL GUI when the spec explicitly contemplates third-party GUIs and third-party Backends as first-class use cases."

### (b) Clauses or design choices that weaken the position

One required revision and two items to monitor.

**R1 — REQUIRED — §2 `session_token` language.** Counsel found that the current session-token mechanism, while sound for security, "creates a soft coupling between the GUI and Backend that a plaintiff could characterise as a 'privileged channel' not available to third-party GUIs… the one design element in the protocol that looks less like a public API and more like a private handshake between two halves of a single program."

Recommended addition (counsel's verbatim suggested text):

> The `session_token` is a standard bearer credential. Any client that can read the connection descriptor file (§1.4) — or that has been provided the token by the operator — may authenticate. The Backend MUST NOT restrict authentication to a specific process identity, binary signature, or launch parent. A Backend operator MAY configure a static token via environment variable for remote or multi-client deployments.

**Status**: Applied as §2.1 of the protocol spec (in expanded normative form covering process identity, binary signature, launch parent, working directory, executable path, code-signing certificate, and the `CHESS_COACH_BACKEND_TOKEN` static-token configuration).

**R2 — RECOMMENDED — §5 `system.log.<level>` topic.** Counsel found that the live log-tail topic "exposes Backend internals to the GUI in a way that could be characterised as 'intimate'" but assessed it as "not a problem as currently specified" because the topic is Debug-Panel-only, push-only, and observational. Belt-and-suspenders recommendation: explicit statement that the topic is advisory only and that no conforming GUI behavior may depend on log content.

**Status**: Applied as §5.1 of the protocol spec.

**Item to monitor — `ground_truth_hash`.** Counsel assessment: "This is fine. It is a standard content-addressable reference pattern (like a git commit hash), not a shared internal data structure." No change required.

### (c) §6 Installation Information obligations triggered by the protocol

> **The protocol itself does not trigger any §6 obligations beyond those already identified in the prior analysis.**
>
> GPL-3.0 §6 Installation Information obligations attach to the distribution of object code in a User Product, not to the protocol the object code speaks. The protocol is a specification document — it is not itself a covered work, and its publication under CC-BY-4.0 is entirely separate from the GPL-3.0 obligations on the GUI binary.
>
> The one §6 question the protocol raises is indirect: does the session_token mechanism constitute a "key" that a user would need to run a modified GUI binary?
>
> The answer is no, for two reasons:
>
> 1. The token is generated fresh at each Backend restart and written to a file on disk. A user who builds and installs a modified GUI binary can read the same `backend.json` file as the original binary — the token is not bound to the original binary's identity.
>
> 2. The token is not a cryptographic key in the §6 sense (i.e., it does not verify the binary's provenance). It is a session credential that any process with file-system access can obtain.
>
> The §6 obligation confirmed in the prior analysis (the auto-updater signing key / tivoization issue) remains the only live §6 concern, and it is unaffected by the protocol design.

---

## Counsel's summary verdict (verbatim)

| Question | Answer |
|---|---|
| Does the protocol support the aggregate position? | **Yes — strongly.** Mechanism and semantics are both clean. Upgrade from "plausibly no, meaningful residual risk" to **"plausibly no, low residual risk."** |
| Any clauses that weaken the position? | One targeted revision required (§2 session_token language). Two items to monitor (log topic, ground_truth_hash) — neither requires changes. |
| Any §6 obligations triggered by the protocol? | **No new obligations.** The session_token is not a §6 "key." Prior §6 analysis (auto-updater) stands unchanged. |

## Counsel's conclusion (verbatim)

> **Conclusion for the project record**: With R1 applied, this protocol contract supports the conclusion that the GUI and Backend are separate works in an aggregate under GPL-3.0 §5. The "intimacy of communication" residual uncertainty identified in the prior analysis is resolved in your favour by the protocol's design. **U1 (GPL boundary decision) may be treated as resolved — not merely conditionally — subject to P1+P2+P3 adoption as binding requirements and R1 being applied before v1.0.0 is published.**

---

## Project status at receipt + application

| Condition | Status |
|---|---|
| P1 (CLA with broad sublicensing grant) | adopted as binding in `legal-opinion-integration.md` §C.1; Apache ICLA+CCLA recommended; CI gate required at Phase 1 |
| P2 (non-blocking auto-updater per §6 Installation Information) | adopted as binding in `08_security/security-strategy.md` post-legal addendum and `legal-opinion-integration.md` §C.2/§H |
| P3 (public protocol spec) | published as `docs/16_protocol/chess-coach-protocol-v1.md` v1.0.0 |
| R1 (§2.1 standard bearer credential language) | **applied to protocol v1.0.0** |
| R2 (§5.1 advisory-only log topic) | **applied to protocol v1.0.0** |
| R3 (Appendix A retained as-is) | no change needed; retained |

**U1 is now fully RESOLVED.** Implementation may begin once U2 (monolith-first plan), U8 (Stockfish-only Phase 1 roster), and U10 (CLA template) are confirmed by the user.
