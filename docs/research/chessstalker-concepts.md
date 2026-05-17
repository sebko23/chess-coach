# ChessStalker — Concept Extraction

**Target**: https://chessstalker.com/
**Founded**: 2024
**Founder**: David Menendez (GitHub: `dmrujas`)
**Endorsement**: Trusted by GM José Cubas (Paraguayan GM, multiple Olympiad participant)
**Tagline**: "Decode your opponent's chess DNA" / "Know your enemy. Win more games."
**Status**: Live, monetized (Free tier + PRO €4.17–6.99/mo)
**Disclaimer**: Not affiliated with Lichess.org or Chess.com

---

## 1. Core Value Proposition

ChessStalker is a **chess opponent-scouting and preparation tool**. Given an opponent's username (Lichess, Chess.com) or FIDE ID, it produces a personalized scouting report exposing the opponent's:

- opening repertoire and weaknesses within it
- patterns of blunders and tactical failures
- behavioral / psychological tendencies
- exploitable comfort zones

It then provides a **practice mode ("Twin Bot")** where the user spars against an AI clone that plays in the opponent's style.

### Stated headline numbers (from landing page + JSON-LD)
- **191K+ online analyses** performed
- **49K+ FIDE analyses** performed
- **11M+ games** in their database
- **1.7M+ FIDE players** indexed
- **180+ countries** covered (FIDE OTB games)
- Multi-language: 11 locales (en, es, de, fr, pt, ru, uk, pl, ko, zh, uz)

### Stated technical methodology
- **Stockfish-powered analysis** at **depth-25 evaluations** (per noscript SEO content)
- Combines online play data (Lichess + Chess.com APIs) with FIDE OTB tournament data
- Privacy-friendly Plausible-style analytics; "no tracking cookies" claimed

### Stated workflow (3-step product narrative)
1. **Search your rival** — by Lichess/Chess.com username or FIDE name/ID
2. **Get their chess DNA** — analyzes thousands of games for weaknesses, psychology, patterns
3. **Prepare & dominate** — personalized scouting report with specific recommendations (e.g. "Play 1.e4 → Rossolimo. Force endgames.")

---

## 2. Specific Psychological / Behavioral Concepts Detected

From UI screenshots, JSON-LD `featureList`, and SEO noscript fallback. Each is what ChessStalker explicitly claims to detect or expose.

| # | Concept Name | Their 1-line description |
|---|---|---|
| 1 | **Stalker Score** | Single number (0–100, gauge UI shows e.g. 73/100) measuring how *exploitable* an opponent is. |
| 2 | **Tilt Detector** | Detects "when they crack under pressure" — flags emotional collapse / loss-of-control patterns under stress. |
| 3 | **Archetype label** | Each player is assigned a named archetype (visible: "The Berserker"). Implies tactical/aggressive/positional/etc. categorization with a small fixed taxonomy. |
| 4 | **ATK / DEF / TIME / MIND quad-stats** | Player profile reduced to four numeric attributes: ATK (attacking strength), DEF (defensive solidity), TIME (clock management), MIND (psychological resilience). |
| 5 | **Phase-by-phase performance** | Wins / draws / losses broken down by game phase (Bullet / Blitz / Rapid / Classical) and apparently by opening/middle/end phase too. |
| 6 | **Opening repertoire breakdown** | Full breakdown of repertoire share (e.g. 1.e4: 72%, 1.d4: 22%, 1.c4: 6%) with weak-spot identification ranked by loss rate. |
| 7 | **Opening blunder map / weak spots** | Identifies the specific openings or sub-lines where opponent blunders most ("where they blunder"). |
| 8 | **Loss-rate per line** | Quantified per-opening loss rate (e.g. "Sicilian Rossolimo: 68% loss rate") used to recommend openings to play against them. |
| 9 | **Time-pressure behavior** | "Pressure on clock after move 25 → flags 12% of games" — detects when opponent's quality degrades under low time. |
| 10 | **Endgame conversion / pawn-ending failure** | "Force endgames — 53% win rate in pawn endings" — flags poor endgame technique. |
| 11 | **Victory Plan** | Composite output: an AI-generated game plan combining recommended opening + recommended phase to target + psychological lever ("Pressure on clock after move 25", "Force endgames"). |
| 12 | **Twin Bot** | A playable AI sparring partner that imitates the opponent's actual openings and style — for preparation drills. |
| 13 | **Nemesis / Favorite Rival** | Identifies players who consistently beat (or are beaten by) the analyzed player. |
| 14 | **Head-to-Head** | Direct historical record between two players (when both indexed). |
| 15 | **Classic Players / Legends Gallery** | Comparative analysis of contemporary play vs 50+ historical legends (Fischer, Kasparov, Tal, Capablanca shown). |
| 16 | **Advanced Repertoire Filters** (PRO) | Slice repertoire by color, time control, recency, rating bracket, etc. |
| 17 | **Endgame Statistics** (PRO) | Win rates by endgame material type. |
| 18 | **Study Mode** (PRO) | Position-by-position deep dive of opponent's games. |
| 19 | **Twin Bot OTB** (PRO, FIDE-only) | Twin Bot built from FIDE OTB games (vs the FREE Twin Bot which uses only online games). |
| 20 | **Patterns** | Generic label covering recurring move sequences and tactical motifs (mentioned in marketing tags: "Openings · Psychology · Patterns"). |

### Implicit but not directly named on landing page
The noscript fallback explicitly lists `"common blunders"` and `"time pressure patterns"` and `"psychological profile"` as core capabilities. The Schema.org `featureList` also names `"Psychological profile detection"` distinctly from opening/blunder analysis, confirming it is a first-class output.

---

## 3. Detection Methodology (as Claimed)

ChessStalker is **closed-source** and does not publish a methods paper. From observable claims:

- **Engine-based**: "Stockfish-powered analysis with depth-25 evaluations" → blunders, evaluation drops, and per-move centipawn-loss are computed via Stockfish.
- **Statistical aggregation**: counts per opening, per phase, per time control. Loss rates are computed across many games.
- **Threshold-based heuristics** (inferred): tilt detection and time-pressure detection are almost certainly heuristic rules on top of (clock-times + post-move CP-loss + result sequence), not ML models — no model card or training data disclosed.
- **Archetype classification** (inferred): likely a small clustering or rule-based assignment on top of ATK/DEF/TIME/MIND features.
- **Stalker Score** (inferred): composite weighted score over (number of detected weaknesses) × (exploitability magnitude). The exact formula is not disclosed.
- **Data sources**: Lichess public API (games, ratings, time controls), Chess.com public API, FIDE-published OTB game databases. They explicitly state "not affiliated" — pure scraping/API consumers.
- **No published peer review**, no published evaluation against ground truth, no published statistical significance criteria.

**Important caveat**: ChessStalker presents psychological labels ("The Berserker", "MIND: 68") as confident outputs. The methodological transparency is **low**; treat psychological outputs as marketing-grade heuristics, not validated psychometric instruments.

---

## 4. Reports / Outputs the User Sees

Observed deliverables (from screenshots):

1. **Player Profile Card**
   - Username + game count ("6,527 games · 3 months")
   - Archetype badge ("The Berserker")
   - Overall Stalker Score gauge (e.g. 73/OUT)
   - 4 numeric attributes: ATK, DEF, TIME, MIND (0–100 each)
   - Time-control rating breakdown (Bullet/Blitz/Rapid/Classical) — Elo + game count
   - Win-rate strip (% OK) + W/D/L counts (e.g. "3124w · 512d · 2891L")
   - Sparkline of recent rating/performance
2. **Opening Analysis card**
   - Bar chart of opening share with % (1.e4 72%, 1.d4 22%, 1.c4 6%)
   - Highlighted weak sub-line with loss rate ("1...c5: 38% loss")
3. **Tilt Detector chart**
   - Time-series line showing performance under pressure (visualization of crack points)
4. **Victory Plan box**
   - 3 concrete recommendations, each tagged:
     - "Play 1.e4 → Sicilian Rossolimo (68% loss rate)"
     - "Pressure on clock after move 25 (flags 12% of games)"
     - "Force endgames (53% win rate in pawn endings)"
5. **Twin Bot launch panel** — playable engine adapted to opponent's ELO + openings
6. **FIDE Database card** — for FIDE-registered opponents, OTB game count, country
7. **Legends Gallery** — comparison vs historical GMs (PRO)
8. **Per-feature PRO unlocks** (visible feature matrix) — Endgame Statistics, Study Mode, Unlimited PGN Downloads, etc.

Outputs are **interactive web cards**, not downloadable PDF reports (except PRO "Unlimited PGN Downloads"). Optimized for fast scanning before a game.

---

## 5. Concepts CHESS COACH Should Adopt

Ranked by signal value. Each with a one-line justification.

1. **Stalker Score / Exploitability Index** — A single headline number is high-impact UX. Even if internally we expose 20 dimensions, distilling them into one "how-beatable-are-they" gauge is excellent product UX for coaching dashboards and self-assessment.
2. **Per-opening loss-rate ranking with weak-line surfacing** — Surfacing "in this opening you/they lose 68% of the time" is the single most actionable insight for repertoire work; CHESS COACH should produce this for both opponent prep and self-improvement (mirror it onto the *user's own* games).
3. **Time-pressure breakdown (post-move-N quality)** — Computing the centipawn-loss curve as a function of remaining time is methodologically straightforward and exposes one of the most actionable weaknesses; this is a clear adopt.
4. **Twin Bot — adversary-style sparring partner** — Replaying against a Maia/Stockfish-tuned model adapted to a target opponent's openings and ELO is technically achievable (Maia + opening book extracted from PGN). This is a *killer* training feature.
5. **Victory Plan / structured "3 levers" recommendation** — Bundling top-3 actionable moves (opening to play, phase to target, psychological lever) into a single coachable plan is excellent pedagogy; aligns with CHESS COACH's coach-narrative vision.
6. **Quad-stat profile (ATK / DEF / TIME / MIND)** — Reducing a player to a small radar/quad makes longitudinal tracking trivial. Useful for showing CHESS COACH users their growth across dimensions; can be regenerated from their own games.
7. **Archetype classification with named labels** — A small (8–12) archetype taxonomy (Berserker, Tactician, Grinder, Theoretician, Defender, Speculator, etc.) is a strong UX hook for user engagement and self-recognition. Should be additive, not replacing detailed analytics.
8. **Tilt detection** — Detecting losing streaks within a session + accompanying CP-loss degradation flags an emotional/cognitive failure mode. High-value for coaching. (Note caveats in §6.)
9. **Endgame conversion stats by material type** — Per-pattern endgame win-rate is a deeply useful self-improvement metric (pawn endings vs. minor-piece endings vs. rook endings).
10. **Head-to-Head + Nemesis detection** — When the user has a recurring opponent (club/online), this is high-utility; should be a first-class CHESS COACH feature.
11. **Comparison vs. classical legends** — Mapping the user's style onto historical GMs is engaging and instructive — "You play most like Petrosian" leads to relevant study recommendations (model games).
12. **Multi-source data fusion (Lichess + Chess.com + FIDE OTB)** — Adopt the principle that one unified player view should aggregate all known game sources, not silo them. Critical architectural decision.
13. **Phase-tagged statistics (Bullet / Blitz / Rapid / Classical)** — Always disaggregate by time control. A player can be vastly different across formats; never average over them.

---

## 6. Concepts to AVOID or Treat Skeptically

1. **Unvalidated psychological labels** — ChessStalker presents archetypes and a "MIND: 68" number with no published validity evidence. CHESS COACH must either (a) publish methodology and uncertainty bands, or (b) explicitly frame these as *heuristic descriptors*, not psychometric measurements. Otherwise we risk overclaiming and damaging user trust.
2. **Single "exploitability" scalar without uncertainty** — A 73/100 score with no confidence interval invites overconfidence. CHESS COACH should always pair scores with sample size + confidence band ("73 ±8, based on 6,527 games").
3. **"Tilt" detection from result sequences alone** — Hard to disentangle tilt from variance in noisy chess data. Must combine (CP-loss spikes + time-usage anomalies + result streaks) and even then label outputs as "possible tilt signal" not diagnosis.
4. **Opponent-targeted preparation as primary framing** — ChessStalker's "stalker" framing is borderline (scouting another player is fine; the marketing language flirts with creepy). CHESS COACH should keep opponent prep as one feature among many; its primary framing should be *self-improvement coaching* (which is the brief).
5. **No documented engine settings beyond "depth 25"** — Depth alone is meaningless without time-per-move, hash, threads, and contempt settings. CHESS COACH must publish full engine config for reproducibility.
6. **Closed methodology** — Their psychological/archetype/score formulas are black boxes. CHESS COACH should be transparent and reproducible.
7. **Mixing online + OTB without weighting** — Lichess Bullet games and OTB Classical games are radically different signal qualities. ChessStalker is unclear about how they're combined; CHESS COACH must be explicit (weighted by time control, sample size, and recency).
8. **"Twin Bot" branding implying perfect replication** — A bot trained on someone's openings does *not* play like them in the middlegame; calling it a "clone" overclaims. CHESS COACH should call this an "opponent-style sparring engine" with documented limitations.
9. **Static archetype labels** — Players change. Locking someone into "Berserker" forever is bad coaching. CHESS COACH's archetypes must be **time-windowed** and **trajectory-aware**.
10. **GDPR/privacy ambiguity around third-party player profiling** — Building dossiers on identifiable named players (especially FIDE OTB players) without their consent is a known concern. CHESS COACH should bias toward analyzing the *user's own* games + their *self-uploaded* opponent data, and should document data handling.

---

## 7. Gaps / Opportunities — What CHESS COACH Can Do Better

1. **Self-coaching primacy** — ChessStalker is opponent-prep first. CHESS COACH's primary user is *the player improving themselves*. Symmetric analysis (apply every metric to the user's own games) is largely missing in ChessStalker.
2. **Coach narrative / prose explanation** — ChessStalker outputs numbers and bars. CHESS COACH can produce GM-level prose explanations ("You blunder most often in IQP positions after move 18 because of recurring back-rank pressure — let's drill these motifs for 2 weeks").
3. **Training planner with feedback loop** — ChessStalker has no training plan. CHESS COACH can convert detected weaknesses into spaced-repetition exercises (and en-croissant already has FSRS infra).
4. **PDF / book ingestion** — ChessStalker has no book/PDF knowledge integration. CHESS COACH's PDF + diagram pipeline gives access to canonical chess literature for grounded explanations.
5. **Multi-engine + Maia / human-like comparison** — ChessStalker mentions Stockfish only. CHESS COACH supporting Lc0, Maia (per ELO), and ensembles produces richer human-vs-engine error analysis.
6. **Repertoire gap & novelty discovery** — ChessStalker exposes *opponent* opening shares but does not (visibly) propose novelties or detect gaps in the *user's* repertoire vs. modern theory. CHESS COACH can.
7. **Longitudinal trajectory** — Show user how ATK/DEF/TIME/MIND have moved over months/years, not just current snapshot.
8. **Causal/counterfactual analysis** — "If you had 3 more minutes per game, your CP-loss after move 30 drops by X." These what-if analyses are absent from ChessStalker.
9. **Calibration + uncertainty** — Always show confidence bands, sample sizes, and statistical significance. Critical for trust and pedagogy.
10. **Explainable archetypes** — When CHESS COACH labels a user, show *which games / which moves / which patterns* led to the label. Transparent reasoning.
11. **Cohort comparison** — Compare user to anonymized cohort of same rating bracket (not just to historical GMs) for realistic peer reference.
12. **Cross-game pattern detection** — Tactical/positional themes recurring across many games ("You miss double attacks involving knights on f4/f5 23% of the time") — exceeds what ChessStalker exposes.
13. **Coach voice memory** — Multi-session memory of what's been worked on, what's improving, what's stuck. ChessStalker has no learning continuity; CHESS COACH's memory subsystem is the differentiator.
14. **Open methodology** — Publish formulas, engine settings, evaluation methodology. Build trust ChessStalker hasn't earned.
15. **Integration with real training** — Link detected weakness → relevant book chapter / PDF page / Lichess study / puzzle theme — closing the loop from diagnosis to action.

---

## Summary Verdict

ChessStalker is **conceptually valuable but methodologically opaque**. Its product is a clean execution of: "engine-evaluate a bunch of someone's games, surface their weaknesses as cards." The interesting innovations are:

- The **Stalker Score / quad-stat / archetype** distillation pattern (great UX)
- The **Twin Bot** style-sparring partner (technically achievable for us)
- The **Victory Plan** structured 3-lever recommendation (good pedagogy template)
- The **time-pressure-as-feature** framing (high-value, easy to implement)

What CHESS COACH must do **differently**: be self-improvement-first (not opponent-prep-first), be transparent about methodology and uncertainty, ground psychological labels in published criteria, integrate book/PDF knowledge for explanation, deliver a coach-narrative voice, and maintain longitudinal training-plan continuity that ChessStalker entirely lacks.
