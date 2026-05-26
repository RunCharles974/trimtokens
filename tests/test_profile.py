"""Tests CLI --profile + collecte StepMetrics dans ProcessResult."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from trimtokens.cleaners import clean
from trimtokens.cleaners.steps import (
    StepMetrics,
    aggregate_metrics,
    default_pipeline,
)
from trimtokens.cli import app
from trimtokens.core import process

runner = CliRunner()


def test_clean_metrics_sink_extends_when_provided() -> None:
    sink: list[StepMetrics] = []
    cleaned, _ = clean(text="hello   world", metrics_sink=sink)
    assert cleaned
    assert len(sink) == len(default_pipeline().steps)
    assert all(isinstance(m, StepMetrics) for m in sink)


def test_clean_metrics_sink_none_means_no_collection() -> None:
    # Avant : retournait (text, stats). Toujours le cas.
    cleaned, stats = clean(text="hello world")
    assert cleaned == "hello world"
    assert stats.cleaned_chars == len("hello world")


def test_aggregate_metrics_sums_per_step() -> None:
    metrics = [
        StepMetrics(name="a", chars_in=100, chars_out=80, duration_ms=1.5),
        StepMetrics(name="b", chars_in=80, chars_out=70, duration_ms=2.0),
        StepMetrics(name="a", chars_in=50, chars_out=40, duration_ms=0.5),
        StepMetrics(name="b", chars_in=40, chars_out=30, duration_ms=1.0),
    ]
    aggregated = aggregate_metrics(metrics)
    assert len(aggregated) == 2

    by_name = {m.name: m for m in aggregated}
    assert by_name["a"].chars_in == 150
    assert by_name["a"].chars_out == 120
    assert by_name["a"].duration_ms == 2.0
    assert by_name["b"].chars_in == 120
    assert by_name["b"].duration_ms == 3.0


def test_aggregate_metrics_preserves_first_occurrence_order() -> None:
    metrics = [
        StepMetrics(name="z", chars_in=10, chars_out=5, duration_ms=0.1),
        StepMetrics(name="a", chars_in=10, chars_out=5, duration_ms=0.1),
        StepMetrics(name="z", chars_in=10, chars_out=5, duration_ms=0.1),
    ]
    aggregated = aggregate_metrics(metrics)
    assert [m.name for m in aggregated] == ["z", "a"]


def test_aggregate_metrics_empty_returns_empty() -> None:
    assert aggregate_metrics([]) == []


def test_process_result_includes_pipeline_metrics(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("hello   world\n\n\n\nfoo bar baz", encoding="utf-8")
    result = process(src)

    assert result.pipeline_metrics
    # Agrégé par nom — `limit_consecutive_newlines` apparaît 2× dans default_pipeline,
    # ce qui collapse à un nom unique après aggregate_metrics.
    expected_unique_step_names = len({s.name for s in default_pipeline().steps})
    assert len(result.pipeline_metrics) == expected_unique_step_names
    assert all(isinstance(m, StepMetrics) for m in result.pipeline_metrics)


def test_cli_profile_flag_prints_pipeline_table(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("hello   world\n\n\n\nfoo", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [str(src), "--out", str(out_dir), "--profile"],
    )
    assert result.exit_code == 0, result.output
    # Titre + headers
    assert "Pipeline de nettoyage" in result.output
    assert "Étape" in result.output
    assert "Chars in" in result.output
    # Step names peuvent être tronqués par Rich (`normalize…`) selon largeur term.
    # On vérifie un préfixe stable + au moins un step name complet (finalize est court).
    assert "normalize" in result.output
    assert "finalize" in result.output


def test_cli_without_profile_omits_pipeline_table(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("hello world", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(app, [str(src), "--out", str(out_dir)])
    assert result.exit_code == 0
    assert "Pipeline de nettoyage" not in result.output


def test_cli_profile_with_quiet_suppresses_table(tmp_path: Path) -> None:
    """--quiet annule l'affichage stats ET profile (cohérence UX)."""
    src = tmp_path / "doc.txt"
    src.write_text("hello world", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(app, [str(src), "--out", str(out_dir), "--profile", "--quiet"])
    assert result.exit_code == 0
    assert "Pipeline de nettoyage" not in result.output
