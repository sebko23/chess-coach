# Legal Brief — GPL-3.0 Boundary Analysis for CHESS COACH

**For**: external counsel specializing in open-source software licensing
**From**: CHESS COACH project lead
**Date**: 2026-05-18
**Estimated time to answer**: 2–4 hours of professional analysis
**Attachments**: `en-croissant-LICENSE.txt` (verbatim GPL-3.0-only as published by the upstream project)

---

## 0. How to read this document

This is a focused legal brief, not a request for general advice. The technical facts are stated concisely so you can apply them to the GPL-3.0 directly. The numbered **Questions** are pointed and intended to be answered individually, with brief reasoning. Where you need to express a confidence level (e.g. "likely", "plausible but contested", "clear"), please do so explicitly.

We will use your answers to choose one of four architectural paths (§4 below) before any production code is written. Cost of a wrong choice discovered later is very high (months of code may need to be relicensed or rewritten), so a clear answer now is worth significantly more than a hedged one later.

---

## 1. Factual context

### 1.1 What CHESS COACH is

A single-user desktop chess coaching application for Windows (later macOS/Linux). It combines:

- a **graphical user interface** (the **"GUI"**) that is a fork of an existing open-source chess GUI project named **en-croissant**, written in Rust + TypeScript/React using the Tauri 2.x framework. **en-croissant is licensed under GPL-3.0-only.** The full license text as published by en-croissant is attached.
- a **backend** of analysis and coaching services (the **"Backend"**) we are writing in Python from scratch. The Backend runs as one or more separate OS processes and provides chess engine analysis (using Stockfish, which is GPL-3.0 itself — see §6), LLM-mediated coaching narration, opening repertoire analysis, training plans, etc.
- the two components communicate over **HTTP and WebSocket on the loopback interface (127.0.0.1)**, using a documented JSON-over-HTTP and JSON-over-WS protocol. There is **no shared address space**, **no dynamic linking**, and **no shared object code** between GUI and Backend processes.

### 1.2 How we intend to modify and distribute

We intend to:

1. **Fork** en-croissant from a pinned upstream tag, add our own new React panels (in a new directory `panels/coach/`) and a small number of new Tauri commands that call the Backend over HTTP. Upstream en-croissant files are touched minimally. The fork's GUI source code will be published publicly. We accept that the fork (i.e. the modified GUI) must be distributed under GPL-3.0-only.
2. **Write the Backend ourselves**, in Python, with no source code borrowed from en-croissant. The Backend depends on independent libraries (FastAPI, python-chess, PaddleOCR, etc.) under permissive licenses (Apache-2.0, MIT, BSD), plus chess engines that are themselves separate executables (Stockfish under GPL-3.0; see §6).
3. **Distribute** the application to end users primarily as a single Windows MSI installer. The installer deploys two executables to disk: (a) `chess-coach-gui.exe` (the Tauri shell, built from the GPL fork) and (b) `chess-coach-backend.exe` (a PyInstaller-bundled Python process containing the Backend code). Together they are referred to in marketing and UI as **"CHESS COACH"**. The installer also drops engine binaries (Stockfish; later optionally Leela) and a Redis-compatible service binary.
4. At runtime: the GUI launches the Backend as a child process via Tauri's `externalBin` / `tauri-plugin-shell` mechanism, then communicates with it strictly over the local HTTP/WS protocol described above.
5. End users **do not see the two binaries as separable**: they install one product, see one application window, and one entry in the Start Menu. They are however able to terminate the Backend process independently, run the Backend alone (it has a CLI), and theoretically substitute a different GUI that speaks the same HTTP/WS protocol.
6. The Backend's source code will be distributed publicly **but** we wish, if legally permissible, to release it under a **permissive license** (likely Apache-2.0) so that it can be reused, embedded, or commercially licensed in other contexts independent of the GPL GUI.
7. We may later additionally offer a hosted (network-served) version of the Backend (multi-user club server). This raises a separate AGPL-3.0 question only if any AGPL component enters the stack — currently none planned, but please flag if any of our planned dependencies would change this.

### 1.3 What we are NOT doing

- We are not linking to en-croissant code from the Backend. The Backend has zero Rust, zero `use` of any en-croissant module, zero FFI calls into the GUI binary.
- We are not relicensing en-croissant. The GUI fork stays GPL-3.0-only.
- We are not removing en-croissant attribution. We will retain upstream copyright notices in modified files and provide the fork's full source on release.
- We are not embedding the Backend code inside the GUI binary; they are physically separate executables.
- We are not using en-croissant's name as our product name ("CHESS COACH" ≠ "en-croissant"), nor claiming endorsement.

---

## 2. The single most important question

**Q1.** Under GPL-3.0-only as published in the attached `en-croissant-LICENSE.txt`, applied to the architecture and distribution described in §1, **does the Backend (`chess-coach-backend.exe`) constitute part of a single combined work** (a "covered work" in GPL-3.0 §0 terminology) **with the GUI fork**, such that the Backend would also be required to be distributed under GPL-3.0-compatible terms?

Please provide a direct answer ("yes", "no", "plausibly yes", "plausibly no", "genuinely uncertain — split court history") and your reasoning, including reference to the specific GPL-3.0 clauses you rely on (we expect §0 "covered work", §5 "convey modified source versions", §5 final paragraph ("aggregate"), and possibly §6).

If the answer depends on facts not in §1, please list those facts.

---

## 3. Sub-questions that elaborate Q1

For each sub-question, please answer briefly (1–3 sentences plus citation) unless deeper analysis is needed.

### 3.1 Combined-work vs aggregate distinction

**Q2.** GPL-3.0 §5's final paragraph defines an "aggregate" as a compilation of a covered work "with other separate and independent works, which are not by their nature extensions of the covered work". In your view, is a Backend that **only exists to enable the GUI's chess-coaching feature set** "by its nature an extension of" the GPL GUI, even though they run as separate processes communicating over a protocol?

**Q3.** Does it matter whether the protocol is **public and documented** (such that a third party could write a replacement GUI or replacement Backend) versus **private and undocumented** (such that the two are de facto inseparable)? We intend the protocol to be public and documented. Please confirm whether that fact, by itself, helps establish independence.

**Q4.** Does it matter whether **the Backend can be run usefully without the GUI** (e.g. via its CLI, or by a third-party GUI)? We intend the Backend to function standalone via a CLI and a documented HTTP API.

**Q5.** Does it matter whether **the GUI can be run usefully without the Backend**? In practice the GUI without the Backend would lose most coaching features but retain en-croissant's original analysis-board functionality. (en-croissant by itself is a usable chess analysis tool; the Backend adds the "coaching" layer.) Please confirm whether this asymmetry helps or hurts the "independence" argument.

### 3.2 Distribution mechanics

**Q6.** Does distributing both binaries in **one Windows MSI installer** (as opposed to two separate downloads from the same website) change the legal analysis? Specifically, does the §5 "aggregate" exception require the medium of distribution to genuinely be "a storage or distribution medium" (e.g. a release server) and not a programmatic installer that purposely glues the two together?

**Q7.** Would it materially help if we provided the Backend as a **separate optional download** that the user installs after the GUI? (Trade-off: worse UX, but cleaner legal separation.) If yes, please describe what "materially help" means quantitatively (e.g. "reduces risk meaningfully" vs "eliminates risk").

**Q8.** Would it help to host the Backend in a **separate code repository** under a different organization on GitHub, even if the same developer team maintains both? (We are willing to do this.)

**Q9.** Under GPL-3.0 §6, distributing object code triggers source-availability obligations. **Does our planned auto-updater for the GUI** (signed Ed25519 updates delivered over HTTPS, replacing only the GUI binary) raise any GPL-3.0 §6 issue beyond the obligation to make the corresponding source publicly available alongside the update? In particular, are there §6 obligations around **encryption keys / DRM-like mechanisms** that signed updates implicate?

### 3.3 Product naming and integration intent

**Q10.** We market the combined product as "CHESS COACH". The GUI binary is `chess-coach-gui.exe` and the Backend is `chess-coach-backend.exe`. Does **the shared brand and the appearance of integration in the user's mental model** weigh into the combined-work analysis under U.S. law (specifically post-*Jacobsen v. Katzer* and FSF interpretive guidance)? If yes, would it help to brand the Backend with a different product name (e.g. "Crumb Backend" or similar) and keep "CHESS COACH" as the GUI's branding only?

**Q11.** Is there case law or settled FSF position on **single-installer distribution + same-brand + functional dependence** that we should be aware of?

### 3.4 Process boundary as a legal boundary

**Q12.** It is widely repeated in the open-source community that **separate processes communicating over IPC** are a sufficient license boundary under the GPL. Please address whether this is:
  - (a) settled law,
  - (b) the FSF's stated position but not court-tested,
  - (c) an unsettled or contested heuristic.

  Please cite the FSF's GPL FAQ entry on this if applicable (we believe this is the entry titled roughly "What is the difference between an 'aggregate' and other kinds of 'modified versions'?") and note where it does or does not match your assessment.

**Q13.** Specifically regarding **Tauri's `externalBin` / `tauri-plugin-shell`** mechanism — where the GPL GUI launches the Backend as a child process at startup and depends on it for primary functionality — does the **act of one binary launching the other** change the analysis vs. the case where the user launches both manually?

### 3.5 The Stockfish question (independent of en-croissant)

The Backend invokes Stockfish (a separate GPL-3.0 executable) over the UCI protocol via stdin/stdout. Stockfish is **not** linked to the Backend; it is a child process the Backend spawns.

**Q14.** Does the Backend's invocation of Stockfish as an external GPL-3.0 process subject the Backend itself to GPL-3.0, independent of the en-croissant question? Our understanding is no (stdin/stdout to a separate executable is the canonical FSF-approved "aggregate" pattern, and Stockfish itself documents this usage as expected) but we would like this confirmed.

**Q15.** Does shipping the Stockfish binary inside our MSI installer change Q14? Stockfish itself is freely redistributable under GPL-3.0 provided we honor source-availability; we can satisfy that by linking to the Stockfish repository in our distribution.

### 3.6 If the answer to Q1 is "yes" or "plausibly yes"

**Q16.** If the Backend is in fact required to be under GPL-3.0-compatible terms, **what are the GPL-3.0-compatible licenses we could choose** for the Backend? In particular:
  - Is **Apache-2.0** GPL-3.0-compatible **as the license of code that is part of a GPL-3.0 covered work**? (We are aware of the FSF's position that Apache-2.0 is compatible with GPL-3.0 but not GPL-2.0; please confirm this still applies in our specific direction.)
  - Is **MIT/BSD-3** acceptable?
  - Is **AGPL-3.0** required if we later offer hosted-service access to the Backend, **even if no AGPL-licensed code is in our stack**?

**Q17.** If we license the Backend under GPL-3.0 itself, can we **also** dual-license it commercially to third parties who want to embed the Backend in a non-GPL product (with a separate GUI of their own)? In other words, does our being the sole copyright holders of the Backend code preserve our right to commercial-license it independently, even though one distribution channel ships it alongside the GPL fork?

**Q18.** If we choose to commercial-license the Backend, does **the existence of contributions from third parties** (community PRs) affect our ability to do so, and what CLA/DCO structure would you recommend to preserve it?

### 3.7 If the answer to Q1 is "no" or "plausibly no"

**Q19.** What **specific architectural or distribution changes**, if any, would **further strengthen** the "separate works" / aggregate position? Examples we are open to:
  - Two separate MSI installers.
  - Backend distributed via `pip` only; GUI installer doesn't bundle it.
  - Different product branding for Backend.
  - Different GitHub organization for Backend.
  - Public protocol specification published as a separate document with its own license (e.g. CC-BY-4.0).

  Please rank these by legal effectiveness (most to least useful) and note any we have not listed.

**Q20.** Conversely, are there any **routine engineering practices** we should **avoid** because they would re-establish a combined-work relationship even if our architecture otherwise looks separate? (E.g. inlining backend protocol stubs into the GUI source, embedding GUI strings inside the Backend, etc.)

### 3.8 Risk and remediation

**Q21.** If we proceed under the assumption "Backend can be Apache-2.0" and later (e.g. 12 months in) discover this was wrong, **what are the practical remediation paths**?
  - (a) Relicense Backend GPL-3.0-only going forward (impacts on contributors who agreed to Apache).
  - (b) Relicense retroactively with all contributor consents.
  - (c) Break the integration (the Backend becomes a genuinely independent product) and bear the engineering cost.
  - Please outline the cost and feasibility of each.

**Q22.** Is there a way to **structure the project from day one** that **preserves optionality** to flip the Backend's license later without re-soliciting contributor consents? (E.g. a CLA assigning copyright to a project entity that retains relicensing rights.)

### 3.9 Trademark and attribution (separate from license)

**Q23.** Does en-croissant have any **trademark registration on the name "en-croissant"** that constrains how our fork describes its lineage? We intend to keep upstream copyright notices in modified source files and credit the upstream project in our user-visible "About" dialog, but use our own brand ("CHESS COACH") as the product name. Is this conventional and safe, or are there pitfalls?

**Q24.** GPL-3.0 §7 allows additional permissions but also allows **certain additional non-permissive terms** including "requirements to preserve specified reasonable legal notices or author attributions". Has en-croissant added any §7 additional terms we should be aware of? (We did not see any in the published LICENSE file but please confirm whether en-croissant's repo or other top-level files (`NOTICE`, `COPYING`, README) impose such terms.)

### 3.10 Practical procedural questions

**Q25.** Is a written legal opinion from you on Q1 something we would receive in (approximately) **one round** (we send you this brief, you send back analysis), or would you expect to need follow-up Q&A? If the latter, can you estimate the additional time?

**Q26.** Is there value in obtaining a **second opinion** on Q1 from a different OSS-licensing specialist? Or is Q1 well-settled enough among practitioners that one opinion suffices?

**Q27.** If your answer to Q1 is "genuinely uncertain", would you recommend we **request a written interpretive statement from the upstream en-croissant author** clarifying their license intent? (We have the author's contact and they appear cooperative.) Would such a statement have any legal weight if a third party later asserted infringement?

---

## 4. Decision matrix — the four paths we will choose among based on your answers

For your reference; you do not need to recommend a path unless asked.

| Path | Description | Conditional on |
|---|---|---|
| **A. GPL-the-stack** | Backend is GPL-3.0-only too. Single license. Zero ambiguity. No commercial-licensing optionality for the Backend. | Default if your answer to Q1 is "yes" or "plausibly yes" and we don't want to redesign. |
| **B. Permissive Backend, current architecture** | Backend stays Apache-2.0 or similar; current single-installer architecture preserved. | Your answer to Q1 is "no" or "plausibly no" **and** the §5 "aggregate" position holds for our specific setup. |
| **C. Permissive Backend, hardened separation** | Backend stays Apache-2.0; we adopt the architectural and distribution changes you recommend in Q19 to strengthen separation. | Your answer to Q1 is "plausibly no" but you recommend hardening; or "genuinely uncertain" but Q19 changes make it "more clearly no". |
| **D. Replace en-croissant** | We rewrite the GUI on a non-GPL base (e.g. write our own Tauri+React GUI from scratch, or fork a chess GUI under MIT/Apache). | Your answer to Q1 is "yes" or "plausibly yes" **and** we want commercial Backend optionality enough to bear the GUI-rewrite cost (several months of engineering). |

---

## 5. Materials attached

- `en-croissant-LICENSE.txt` — verbatim GPL-3.0-only as published by the upstream project (full text, 674 lines). This is the GPL-3.0 text dated 29 June 2007 as published by the FSF.

## 6. Materials available on request

- Architecture documentation describing how GUI and Backend communicate (the actual HTTP/WS protocol contract).
- Repository structure plan showing physical separation of source trees.
- en-croissant repository URL and the specific tag we plan to fork from.
- A list of every dependency in the planned Backend with its license, if you want to verify no AGPL/SSPL/copyleft sneaks in.

Please let us know whether any of these would help your analysis; we will provide them on request.

---

## 7. What we are asking you to do

In order of importance:

1. **Answer Q1 directly** with confidence level and reasoning.
2. **Answer Q16–Q22** so we can pick a path under either branch.
3. **Answer Q2–Q15** to the extent your analysis depends on them.
4. **Answer Q23–Q27** as procedural cleanup.
5. **Flag any factual gap** in §1 that would change your analysis.
6. **Recommend a path** from §4 if you have a strong view, but only if asked or if your view is strong.

Thank you. Please bill us your standard hourly rate for the time this takes; we expect 2–4 hours and will not be surprised if it is more given Q19.
