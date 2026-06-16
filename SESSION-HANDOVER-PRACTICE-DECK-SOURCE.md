# SESSION-HANDOVER: Practice Panel Deck Source

**Status:** Documentation only — NOT a bug
**Date:** 2026-06-16
**Session:** Practice panel "stuck on UNSEEN: 1" investigation

## TL;DR

The Practice panel builds its card deck from the **currently loaded PGN tree** in the active tab, **NOT** from the SQLite `training_cards` table. If no PGN is loaded in the Practice tab, the deck is empty and the panel shows `UNSEEN: 1` with no progress. This is **correct behavior**, not a bug.

## Data Flow

```
Practice Tab (loaded PGN)
  └─> currentTabAtom (Jotai)
      └─> getTabFile(currentTab) → tabFile.path
          └─> deckAtomFamily({ file: tabFile.path, game: tabGame })
              └─> positions: Position[] in localStorage
                  └─> useEffect: buildFromTree(root, orientation, start)
                      └─> syncDeck() / setDeck() with new positions
                          └─> getCardForReview(positions, { random: false })
                              └─> filters by `position.card.due <= now`
                                  └─> returns first due card (or null if none due)
```

## Key Code References

- `apps/desktop/src/components/panels/practice/PracticePanel.tsx:78-84`
  - Reads `tabFile` from current tab; if null, `file: ""` → empty deck
- `apps/desktop/src/components/panels/practice/PracticePanel.tsx:90-120`
  - useEffect that builds deck from `buildFromTree(root, orientation, start)`
- `apps/desktop/src/components/files/opening.ts:83-94`
  - `getCardForReview(positions, options)` filters by due date
- `apps/desktop/src/state/atoms.ts:478-489`
  - `deckAtomFamily` keyed by `{ file, game }`, backed by localStorage

## What the SQLite `training_cards` Table IS

The `training_cards` table (1534 cards for `ebassti` as of this session) is a **separate cache** populated by the analysis pipeline when games are analyzed. It is **NOT** consulted by the Practice panel UI. The Practice panel only ever reads from the PGN tree in the active tab.

## How to Make Practice Panel Show Cards

**Load a PGN into the Practice tab first.**

1. Open the **Repertoire** tab and import/add a PGN (opening file, repertoire, etc.)
2. Or open the **Files** tab and load a PGN
3. Navigate to the **Practice** tab
4. The panel will build positions from the PGN's tree via `buildFromTree()`
5. Cards will appear in the review queue with FSRS scheduling

## Symptom → Diagnosis

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Practice panel shows `UNSEEN: 1` and never advances | No PGN loaded in the Practice tab | Load a PGN in Repertoire or Files first |
| Practice panel shows correct card count but review doesn't progress | FSRS scheduling bug (card.due always in future) | Check `position.card.due` values in localStorage |
| Practice panel crashes on mount | Missing `TreeStateProvider` wrapper | Wrap in `PracticePage` (see commit `919d441`) |

## Why This Document Exists

This was misdiagnosed in a prior session as a potential "no deck loaded" bug. The 1534 cards in `training_cards` were verified to exist, but they have **no relationship** to what the Practice panel displays. Future sessions should NOT repeat this investigation.

If a future bug report says "Practice panel doesn't show my training cards," the answer is: **it's not supposed to**. The panel uses the PGN tree, not SQLite.
