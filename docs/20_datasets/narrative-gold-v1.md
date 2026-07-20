# Narrative Gold v1 -- Curation Guide

**Status:** BBF-69.2 curation kit. The shipped corpus is still a synthetic placeholder until a domain expert replaces it.
**Path:** `tests/gold/narrative/v1/corpus.json`
**Loader:** `chess_coach.datasets.narrative_gold`

## Goal

Create an initial set of 20-30 positions whose explanations can ground the narration pipeline. Each entry must pair a legal FEN with a 50-200 word coaching explanation and a precise provenance citation.

This is a human curation task. Automation may check structure, FEN validity, duplicate IDs, and duplicate positions, but it must not invent book quotations, page numbers, game annotations, or copyright status.

## Acceptance bar

Every entry must satisfy all of these conditions:

1. **Useful position.** The position illustrates a concrete strategic, tactical, or endgame lesson rather than merely naming an opening.
2. **Original explanation.** Write a concise paraphrase in your own words. Do not paste long passages from a book or website.
3. **Precise provenance.** Cite the source precisely enough that another curator can locate it. Never guess a title, author, chapter, page, game, event, year, or URL.
4. **Legal FEN.** The position must parse with `chess.Board(fen)`, and `board.is_valid()` must be true.
5. **Unique identity.** IDs are dense (`NG-v1-0001`, `NG-v1-0002`, ...) and both ID and FEN are unique within v1.
6. **No placeholder markers.** A completed entry must not contain `STUB`, `PLACEHOLDER`, `n/a`, or `replace via BBF-69.2`.
7. **Balanced seed.** The completed 20-30 entry seed should cover at least:
   - 5 opening lessons;
   - 10 middlegame or tactical lessons;
   - 5 endgame lessons;
   - 2 distinct source types;
   - 3 distinct source works or games.

## Entry schema

```json
{
  "id": "NG-v1-0001",
  "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 4 3",
  "narrative_explanation": "Write a 50-200 word original coaching explanation here. Explain what matters in the position, why it matters, and what plan or decision a student should understand.",
  "source": {
    "type": "book",
    "title": "Exact title",
    "author": "Exact author",
    "chapter": "Exact chapter or section",
    "page": "Exact page in the cited edition",
    "edition": "Publisher and year when page numbering is edition-specific"
  },
  "tags": ["opening", "development", "center"]
}
```

Required top-level fields:

- `id`: string matching `NG-v1-NNNN`;
- `fen`: standard six-field FEN;
- `narrative_explanation`: original coaching prose, 50-200 words;
- `source`: object with a supported `type` and the type-specific fields below;
- `tags`: optional list of short lowercase tags.

## Source types

### Book

```json
{
  "type": "book",
  "title": "Exact title",
  "author": "Exact author",
  "chapter": "Exact chapter or section",
  "page": "Exact page",
  "edition": "Publisher and year"
}
```

`edition` is required whenever another edition could use different page numbers.

### GM game or published game annotation

```json
{
  "type": "gm_game",
  "title": "White - Black",
  "author": "Annotator name or source publication",
  "event": "Exact event",
  "year": "YYYY",
  "round": "Round when known",
  "url": "Stable source URL when the source is online"
}
```

Use `author` for the annotator or publication, not for either player. Omit optional fields instead of filling them with `n/a`.

### Online article or study

```json
{
  "type": "online_article",
  "title": "Exact article or study title",
  "author": "Exact author",
  "url": "Stable canonical URL",
  "accessed": "YYYY-MM-DD"
}
```

Only use material whose licensing and quotation terms you have checked. Prefer paraphrase even when quotation is allowed.

## Curation workflow

1. Pick one lesson and record the source before writing the explanation.
2. Reconstruct or copy the exact position, then verify the FEN in a chess GUI or with python-chess.
3. Write an original 50-200 word explanation answering:
   - What is the position's central feature?
   - Why does that feature matter?
   - What plan, candidate move, or warning should a student retain?
4. Assign the next dense ID and 2-6 useful tags.
5. Replace one placeholder object in `corpus.json`; do not append real entries after placeholder entries.
6. Run the validation command below after every small batch.
7. When all placeholders are gone, update `_metadata` so it describes the real corpus and remove `_metadata.WARNING`.
8. Run the focused tests and inspect the final diff before committing.

## Validation

From the repository root, using an isolated project environment:

```bash
python scripts/validate_narrative_gold.py
python scripts/validate_narrative_gold.py --json
pytest tests/unit/test_narrative_gold.py -q
```

On this Windows host, invoke the project interpreter explicitly if `python` is not available, for example:

```powershell
.\.venv\Scripts\python.exe scripts\validate_narrative_gold.py
.\.venv\Scripts\python.exe -m pytest tests\unit\test_narrative_gold.py -q
```

The strict validator fails while any placeholder marker remains. That is intentional: BBF-69.2 is not complete until the real corpus has replaced every stub and contains 20-30 entries.

## Review checklist

Before declaring BBF-69.2 complete:

- [ ] 20-30 entries load successfully.
- [ ] Every FEN parses.
- [ ] No duplicate IDs or FENs.
- [ ] IDs are dense and ordered from `NG-v1-0001`.
- [ ] Every explanation is 50-200 words.
- [ ] Every source has all required fields for its type.
- [ ] No placeholder marker remains anywhere in the corpus.
- [ ] `_metadata.WARNING` has been removed.
- [ ] The seed meets the phase/source balance in the acceptance bar.
- [ ] Every citation was manually checked against the cited source.
- [ ] `scripts/validate_narrative_gold.py` exits 0.
- [ ] `pytest tests/unit/test_narrative_gold.py -q` passes.

## Out of scope

- Automatically generating the 20-30 explanations.
- Scraping copyrighted books or bypassing access controls.
- Fabricating citations from model memory.
- Wiring the corpus into `services/chess_coach/narration/pipeline.py`; that is BBF-69.3.
- Nearest-neighbour retrieval or embeddings; BBF-69.3 must define that retrieval contract.

## Related documentation

- [`L2-gold-v1.md`](L2-gold-v1.md) -- versioned gold-corpus conventions.
- [`../16_audit/BBF-68.1-candidate-survey-2026-07-17.md`](../16_audit/BBF-68.1-candidate-survey-2026-07-17.md) -- Phase 6 gap analysis and BBF-69 sequence.
- [`../10_roadmap/phase-plan-v2.md`](../10_roadmap/phase-plan-v2.md) -- project roadmap.
