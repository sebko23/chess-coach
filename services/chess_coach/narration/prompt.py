"""Build the grounded-narration system + user prompt from an AnalysisResult."""
from __future__ import annotations

from chess_coach.protocol_types.analysis import AnalysisResult

SYSTEM_PROMPT = """\
You are a chess coach. You must ground every coaching claim in the provided engine analysis.

CITATION RULES (mandatory):
- Every move you mention must appear in <move> tags: <move>Nd4</move>
- Every evaluation you mention must appear in <eval> tags: <eval>+1.3</eval>
- You may not claim a move is "strong", "winning", or "losing" unless the engine evaluation
  supports it. Use the provided scores as your only source of truth for evaluations.
- Do not invent moves, lines, or variations not present in the analysis below.

Keep your narration under 150 words. Focus on the most instructive line."""


def format_analysis_for_prompt(result: AnalysisResult) -> str:
    lines = [f"Position: {result.fen}"]
    for i, pv in enumerate(result.pvs, 1):
        if pv.score.kind == "mate":
            score_str = f"mate in {pv.score.value}"
        else:
            score_str = f"{pv.score.value / 100:+.2f}"
        moves_str = " ".join(pv.moves[:6])
        lines.append(f"PV{i} ({score_str}): {moves_str}")
    lines.append(f"Depth: {result.depth_reached} | Engine: {result.engine_id}")
    return "\n".join(lines)


def build_user_prompt(result: AnalysisResult) -> str:
    return (
        "ENGINE ANALYSIS (ground truth — cite only from this):\n"
        f"{format_analysis_for_prompt(result)}"
    )
