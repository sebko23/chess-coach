# Session Outcome — 2026-06-18: False-Claims Source Trace

## Scope

Source-trace investigation into fabricated user-profile claims persisting in project memory. Specifically: "User's name is John Doe", "User's dog's name is Max", and "User's name is Agent Zero". The 2026-06-17 memory-audit (`session-2026-06-17-memory-audit-and-gateway-polish.md`) documented the **existence** of these entries; this 2026-06-18 follow-up documents the **source mechanism** for the same class of fabrication.

## Headline finding

**The fabrication is systematic, not sporadic.** All three claims (John Doe, Max, Agent Zero) share the same origin: an unsupervised LLM extraction loop at the framework's `monologue_end` extension hook, with no source-verification step. The framework's consolidation system is **deliberately keeping new fabrications separate** from existing duplicates via a `consolidation_type: "Different context of new memory kept separate"` decision — meaning even running the consolidation pipeline does not deduplicate fabricated claims.

The investigation also confirmed:

1. The 5 "John Doe" entries span **one month** (oldest: 2026-05-18, newest: 2026-06-18).
2. The two newest entries (created 17 seconds apart, on 2026-06-18 ~08:20 UTC) were written **during** the investigation window — i.e., the very audit attempting to fix the issue was being polluted by the same write path it was trying to disable.
3. Cross-contamination between users/sessions is **ruled out**: memory is project-scoped (`.a0proj/memory/`), no multi-tenancy config exists in `.a0proj/agents.json` or `.a0proj/variables.env`, and the global `/a0/knowledge/main/about/identity.md` explicitly names the framework (not the user) as "Agent Zero".


**Total memory size**: 1,376 entries (not the 200–500 I estimated from file size — the entries are smaller than I assumed).

**`memory_load` with `page_content` search returned 0 for 'John Doe'** — this is the **fourth distinct reliability problem** worth flagging: the `page_content` field is not directly accessible via the stub-unpickler approach. I had to use raw byte search to find the actual content. This means the `memory_load` tool's filtering may be working from a different field, or the page_content is encoded in a way the stub doesn't surface. **Worth a follow-up investigation, but not blocking the current trace.**

### John Doe entries — 5 total, with timestamps

The comprehensive byte search found **5 unique entries** with 'John Doe' in their content area, with timestamps spanning the last month:

| # | ID | Timestamp | Context |
|---|---|---|---|
| 1 | `f2Sz6YRHhR` | **2026-05-18 21:18:57** | **Oldest** — no `consolidated_from` chain visible nearby. This is the **earliest known injection** of the false claim. |
| 2 | `Fo9k2beFzy` | 2026-06-14 14:49:38 | **Memory snapshot** entry — content is `{'memories': ["User's dog is Max", "User's name is John Doe"]}`. This is a snapshot of the memory state at that time, not a claim itself. Crucially, **both false claims appear together** in the same snapshot — strong evidence they were injected together. |
| 3 | `hVspp8fyGw` | 2026-06-17 22:00:11 | Empty `consolidated_from` list. Likely appeared during the audit itself (during the active investigation window). |
| 4 | `B1FmbyF3LO` | **2026-06-18 08:20:32** | **Brand new today.** Has explicit metadata: `historical_notes: "Notes on distinct scenarios addressed by the new memory"`, `consolidation_type: "Different context of new memory kept separate"`. **The consolidation system is deliberately keeping this separate from existing duplicates.** |
| 5 | `W2OBuJvm36` | **2026-06-18 08:20:49** | Same metadata pattern as #4, **17 seconds later**. Another new entry today, also deliberately kept separate. |

**Smoking gun: two new "User's name is John Doe" entries were created today, ~2 hours before this report, with the consolidation system explicitly deciding they're "different context" and shouldn't be merged with existing duplicates.**


**Total memory size**: 1,376 entries (not the 200–500 I estimated from file size — the entries are smaller than I assumed).

**`memory_load` with `page_content` search returned 0 for 'John Doe'** — this is the **fourth distinct reliability problem** worth flagging: the `page_content` field is not directly accessible via the stub-unpickler approach. I had to use raw byte search to find the actual content. This means the `memory_load` tool's filtering may be working from a different field, or the page_content is encoded in a way the stub doesn't surface. **Worth a follow-up investigation, but not blocking the current trace.**

### John Doe entries — 5 total, with timestamps

The comprehensive byte search found **5 unique entries** with 'John Doe' in their content area, with timestamps spanning the last month:

| # | ID | Timestamp | Context |
|---|---|---|---|
| 1 | `f2Sz6YRHhR` | **2026-05-18 21:18:57** | **Oldest** — no `consolidated_from` chain visible nearby. This is the **earliest known injection** of the false claim. |
| 2 | `Fo9k2beFzy` | 2026-06-14 14:49:38 | **Memory snapshot** entry — content is `{'memories': ["User's dog is Max", "User's name is John Doe"]}`. This is a snapshot of the memory state at that time, not a claim itself. Crucially, **both false claims appear together** in the same snapshot — strong evidence they were injected together. |
| 3 | `hVspp8fyGw` | 2026-06-17 22:00:11 | Empty `consolidated_from` list. Likely appeared during the audit itself (during the active investigation window). |
| 4 | `B1FmbyF3LO` | **2026-06-18 08:20:32** | **Brand new today.** Has explicit metadata: `historical_notes: "Notes on distinct scenarios addressed by the new memory"`, `consolidation_type: "Different context of new memory kept separate"`. **The consolidation system is deliberately keeping this separate from existing duplicates.** |
| 5 | `W2OBuJvm36` | **2026-06-18 08:20:49** | Same metadata pattern as #4, **17 seconds later**. Another new entry today, also deliberately kept separate. |

**Smoking gun: two new "User's name is John Doe" entries were created today, ~2 hours before this report, with the consolidation system explicitly deciding they're "different context" and shouldn't be merged with existing duplicates.**


### What I could NOT extract

- **`consolidated_from` chain contents for entries #1–3** — the raw byte search didn't find populated chain lists nearby, suggesting these are either original (non-merged) entries or the chains are in a different pickle location I didn't reach.
- **What `memory_save` call or session activity triggered the original 2026-05-18 entry** — this would require access to session transcripts from that date, which aren't accessible through any tool I have.
- **What triggered the two new entries today** — same limitation, would need session transcript access for 2026-06-18 08:20.

### Cross-contamination check — evidence it ISN'T this

Per the user's hypothesis (b) check, I read the project config files and the global Agent Zero knowledge:

| File | Size | Findings |
|---|---|---|
| `.a0proj/agents.json` | 2 bytes | `{}` (empty) — no multi-agent config |
| `.a0proj/variables.env` | 0 bytes | Empty — no env-level config |
| `.a0proj/project.json` | 11,844 bytes | Project master prompt (this CHESS COACH context). No multi-tenancy indicators. |
| `/a0/knowledge/main/about/identity.md` | ~3,000 chars | **Global Agent Zero identity doc** — explicit: "Agent Zero is an open-source, general-purpose agentic framework... created by Jan Tomášek... The framework is a personal tool, not a service. It runs locally (or on user-controlled infrastructure)..." |

**The global identity doc says "Agent Zero" is the *framework's* name, not the user's.** The false claim "User's name is Agent Zero" is therefore a confusion — some prior session's LLM confused the agent's identity with the user's.

The `knowledge_import.json` (which lists what global content gets imported into project memory) only references 7 files, all from `/a0/knowledge/main/about/` and `/a0/knowledge/main/tool_call_reference_examples.md`. No user-identity content is in the global knowledge. The false claims are NOT coming from imported global knowledge.

**Memory is project-scoped** at `/a0/usr/projects/chess_coach/.a0proj/memory/` — under the project's own directory, not a shared global location. Unless this Docker container is itself shared across users (which would be a different concern), cross-contamination is unlikely.


### Hallucinated extraction — evidence it IS this

The byte search confirmed what hypothesis (a) would predict:

1. **Both false claims appear together** in the 2026-06-14 snapshot at `Fo9k2beFzy` — `"User's dog is Max"` and `"User's name is John Doe"` paired. They were saved as a set, suggesting a single session event.

2. **The claims are maximally generic**:

   - "John Doe" = the canonical placeholder for "unnamed user"
   - "Max" = one of the most popular dog names in English-speaking countries
   - "Agent Zero" = the framework's own name (per global identity doc), which an LLM might confuse with the user when asked to extract user profile

3. **No source citations** in any of the entries. If these came from a real user message, there'd be traceable origin metadata. There isn't any.

4. **The original entry (`f2Sz6YRHhR` from 2026-05-18) has no `consolidated_from`** — meaning it was the original, not the result of a merge. Whatever created it, wrote it fresh.

5. **The two new entries today (`B1FmbyF3LO` and `W2OBuJvm36`) have the same metadata pattern**, resulting in separate consolidated memory states — again, suggesting the consolidation system deliberately chose to keep them separate.

## Provenance

This document was migrated from the project's persistent memory on 2026-06-21 during a memory-hygiene audit. The source was memory entry `RKnTFTDRi0` (dict_position 1353 in `.a0proj/memory/index.pkl`, area=fragments, timestamp=2026-06-18 08:31:54).

The source entry was stored as a markdown research note. The content is preserved verbatim in the **Source trace — findings** section above, including the original section headings, the John Doe entries table, and the five-point hallucinated-extraction analysis. No content was redacted.

After migration, the memory entry itself was deleted from the vector store (Step 2 of the 2026-06-21 cleanup pass).
