"""BBF-86.7 corpus-version contract tests."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from chess_coach.datasets.archetype_gold import load_archetype_gold_with_metadata
from chess_coach.datasets.narrative_gold import load_narrative_gold_with_metadata
from chess_coach.profile.archetypes import resolve_archetype_gold_version

_VERSION_LOGGER = "chess_coach.datasets.corpus_version"


def _write_archetype_corpus(base: Path, version: str, metadata: object) -> None:
    corpus_dir = base / version
    corpus_dir.mkdir()
    corpus: dict[str, object] = {"schema_version": 1, "entries": []}
    if metadata is not None:
        corpus["_metadata"] = metadata
    (corpus_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")


def _write_narrative_corpus(base: Path, version: str, metadata: object) -> None:
    corpus_dir = base / version
    corpus_dir.mkdir()
    corpus: dict[str, object] = {"schema_version": 1, "entries": []}
    if metadata is not None:
        corpus["_metadata"] = metadata
    (corpus_dir / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")


def test_archetype_version_mismatch_warns_without_refusing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_archetype_corpus(tmp_path, "v0", {"version": "v9"})
    with caplog.at_level(logging.WARNING, logger=_VERSION_LOGGER):
        raw = load_archetype_gold_with_metadata("v0", base_path=tmp_path)
    assert raw["entries"] == []
    assert "archetype gold corpus version mismatch" in caplog.text
    assert "requested 'v0'" in caplog.text
    assert "'v9'" in caplog.text


def test_narrative_version_mismatch_warns_without_refusing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_narrative_corpus(tmp_path, "v2", {"version": "v1"})
    with caplog.at_level(logging.WARNING, logger=_VERSION_LOGGER):
        raw = load_narrative_gold_with_metadata("v2", base_path=tmp_path)
    assert raw["entries"] == []
    assert "narrative gold corpus version mismatch" in caplog.text
    assert "requested 'v2'" in caplog.text
    assert "'v1'" in caplog.text


def test_absent_metadata_warns_without_refusing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_archetype_corpus(tmp_path, "v0", None)
    _write_narrative_corpus(tmp_path, "v2", None)

    with caplog.at_level(logging.WARNING, logger=_VERSION_LOGGER):
        archetype = load_archetype_gold_with_metadata("v0", base_path=tmp_path)
        narrative = load_narrative_gold_with_metadata("v2", base_path=tmp_path)

    assert archetype["entries"] == []
    assert narrative["entries"] == []
    assert "archetype gold corpus version is unverifiable" in caplog.text
    assert "narrative gold corpus version is unverifiable" in caplog.text
    assert "no _metadata object" in caplog.text


def test_missing_or_malformed_versions_warn_without_refusing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_archetype_corpus(tmp_path, "v0", {"WARNING": "no version"})
    _write_narrative_corpus(tmp_path, "v2", {"version": 2})
    with caplog.at_level(logging.WARNING, logger=_VERSION_LOGGER):
        archetype = load_archetype_gold_with_metadata("v0", base_path=tmp_path)
        narrative = load_narrative_gold_with_metadata("v2", base_path=tmp_path)
    assert archetype["entries"] == []
    assert narrative["entries"] == []
    assert "archetype gold corpus version is missing" in caplog.text
    assert "narrative gold corpus version is malformed" in caplog.text


def test_matching_versions_do_not_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write_archetype_corpus(tmp_path, "v0", {"version": "v0"})
    _write_narrative_corpus(tmp_path, "v2", {"version": "v2"})
    with caplog.at_level(logging.WARNING, logger=_VERSION_LOGGER):
        load_archetype_gold_with_metadata("v0", base_path=tmp_path)
        load_narrative_gold_with_metadata("v2", base_path=tmp_path)
    assert caplog.text == ""


def test_shipped_corpora_declare_their_versions() -> None:
    archetype = load_archetype_gold_with_metadata("v0")
    narrative = load_narrative_gold_with_metadata("v2")
    assert archetype["_metadata"]["version"] == "v0"
    assert narrative["_metadata"]["version"] == "v2"


def test_shipped_v0_metadata_tracks_shape_curated_and_tilt_features() -> None:
    """Shipped v0 metadata must describe its mixed provenance and metrics."""
    raw = load_archetype_gold_with_metadata("v0")
    metadata = raw["_metadata"]
    shape_entries = [
        entry for entry in raw["entries"]
        if entry.get("_provenance", {}).get("strategy")
        == "synthetic_shape_curated"
    ]
    assert metadata["n_shape_curated_entries"] == len(shape_entries) == 8
    assert metadata["metric_methodology"] == (
        "services.chess_coach.profile.stats.<6 metrics> + "
        "services.chess_coach.profile.tilt.sequence_based_tilt"
    )
    assert "ARCHETYPE_TRAITS (8 entries)" in metadata["bootstrap_label_strategy"]
    assert all(
        "sequence_based_tilt" in entry["metrics"]
        for entry in raw["entries"]
        if entry["archetype_label"] == "Tilter"
    )


def test_archetype_runtime_version_defaults_to_v0_and_can_be_overridden() -> None:
    assert resolve_archetype_gold_version({}) == "v0"
    assert resolve_archetype_gold_version({"CHESS_COACH_ARCHETYPE_GOLD_VERSION": ""}) == "v0"
    assert (
        resolve_archetype_gold_version(
            {"CHESS_COACH_ARCHETYPE_GOLD_VERSION": "hand-curated-v0"}
        )
        == "hand-curated-v0"
    )


def test_small_corpus_normalizes_votes_by_effective_neighbors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A two-entry corpus produces normalized vote shares, not 2/3."""
    from chess_coach.datasets.archetype_gold import load_archetype_gold
    from chess_coach.profile.archetypes import cluster_archetypes

    monkeypatch.setenv("CHESS_COACH_ARCHETYPE_GOLD_VERSION", "hand-curated-v0")
    for entry in load_archetype_gold("hand-curated-v0"):
        result = cluster_archetypes(dict(entry.metrics))
        assert result.label == entry.archetype_label
        assert result.confidence >= 0.3
        assert sum(result.archetype_scores.values()) == pytest.approx(1.0)
        assert result.archetype_scores[entry.archetype_label] == pytest.approx(0.5)
        assert result.archetype_scores["Tactician"] == pytest.approx(0.5)
        assert result.archetype_scores["Specialist"] == pytest.approx(0.5)
        assert result.effect_size.d is not None
        assert result.passes_b4_gate is True


def test_docker_build_and_runtime_versions_are_coupled() -> None:
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "ARG NARRATIVE_VERSION=v2" in dockerfile
    assert "ARG ARCHETYPE_VERSION=v0" in dockerfile
    assert (
        "COPY tests/gold/narrative/${NARRATIVE_VERSION}/ "
        "/app/tests/gold/narrative/${NARRATIVE_VERSION}/"
    ) in dockerfile
    assert (
        "COPY tests/gold/archetypes/${ARCHETYPE_VERSION}/ "
        "/app/tests/gold/archetypes/${ARCHETYPE_VERSION}/"
    ) in dockerfile
    assert "CHESS_COACH_NARRATIVE_GOLD_VERSION=${NARRATIVE_VERSION}" in dockerfile
    assert "CHESS_COACH_ARCHETYPE_GOLD_VERSION=${ARCHETYPE_VERSION}" in dockerfile


def test_archetype_generator_emits_durable_version_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real archetype generator must persist the corpus version."""
    from scripts import curate_archetype_gold_auto as generator

    import chess_coach.profile as profile

    tests_path = str(Path(__file__).resolve().parents[2] / "tests")
    if tests_path not in sys.path:
        sys.path.insert(0, tests_path)
    import gold.archetypes_with_analyses_fixtures as fixtures

    source = tmp_path / "players.pgn"
    source.write_text("[Event \"test\"]\n", encoding="utf-8")
    players = [
        generator.PgnPlayer("alpha", 30, source),
        generator.PgnPlayer("beta", 30, source),
    ]
    monkeypatch.setattr(generator, "pick_top_players", lambda *args, **kwargs: players)
    monkeypatch.setattr(fixtures, "build_corpus_db", lambda *args, **kwargs: None)

    bootstrap_calls: list[dict[str, object]] = []

    def spy_knn(
        *args: object, **kwargs: object
    ) -> tuple[str, float, dict[str, float], float]:
        bootstrap_calls.append(kwargs)
        return "Tactician", 1.0, {}, 0.0

    monkeypatch.setattr(
        "chess_coach.profile.archetypes._knn_classify",
        spy_knn,
    )

    def metric(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(point_estimate=0.5)
    for name in (
        "tactical_vs_positional_bias",
        "time_pressure_quality",
        "opening_comfort",
        "conversion_ability",
        "blunder_rate_vs_rating",
        "decision_fatigue",
    ):
        monkeypatch.setattr(profile, name, metric)
    monkeypatch.setattr(
        "chess_coach.profile.tilt.sequence_based_tilt",
        lambda *args, **kwargs: SimpleNamespace(point_estimate=0.0),
    )

    output = tmp_path / "v0" / "corpus.json"
    output.parent.mkdir(parents=True)
    preserved_metrics = {
        "tactical_vs_positional_bias": 0.78,
        "time_pressure_quality": 0.05,
        "opening_comfort": 1.0,
        "conversion_ability": 0.0,
        "blunder_rate_vs_rating": 0.18,
        "decision_fatigue": 0.0,
    }
    preserved_entry = {
        "id": "AG-v0-0099",
        "archetype_label": "Tactician",
        "metrics": preserved_metrics,
        "_provenance": {
            "strategy": "synthetic_shape_curated",
            "archetype_trait_source": "ARCHETYPE_TRAITS[Tactician]",
        },
    }
    output.write_text(
        json.dumps({
            "schema_version": 1,
            "_metadata": {"version": "v0", "provenance": "auto"},
            "entries": [preserved_entry],
        }),
        encoding="utf-8",
    )
    generator.curate_v02([source], output, quiet=True)
    corpus = json.loads(output.read_text(encoding="utf-8"))
    assert corpus["_metadata"]["version"] == "v0"
    assert corpus["_metadata"]["metric_methodology"] == (
        "services.chess_coach.profile.stats.<6 metrics> + "
        "services.chess_coach.profile.tilt.sequence_based_tilt"
    )
    generated_entries = [
        entry
        for entry in corpus["entries"]
        if entry.get("_provenance", {}).get("player_name")
    ]
    assert len(generated_entries) == 2
    assert all(
        "sequence_based_tilt" in entry["metrics"]
        for entry in generated_entries
    )
    assert len(bootstrap_calls) == 2
    assert all(call.get("k") == 3 for call in bootstrap_calls)
    assert all(call.get("corpus_version") == "v1" for call in bootstrap_calls)
    assert {entry["id"] for entry in corpus["entries"]} == {
        "AG-v0-0100",
        "AG-v0-0101",
        "AG-v0-0099",
    }
    regenerated_preserved = next(
        entry for entry in corpus["entries"] if entry["id"] == "AG-v0-0099"
    )
    assert regenerated_preserved["archetype_label"] == "Tactician"
    assert regenerated_preserved["metrics"] == preserved_metrics
    assert (
        regenerated_preserved["_provenance"]["strategy"]
        == "synthetic_shape_curated"
    )
    assert corpus["_metadata"]["n_shape_curated_entries"] == 1
