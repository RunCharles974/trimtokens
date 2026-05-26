"""Smoke tests Phase 0 : vérifie que le package s'importe et expose les bons symboles."""

from __future__ import annotations


def test_package_importable() -> None:
    import trimtokens

    assert trimtokens.__version__ == "0.1.0"


def test_models_importable() -> None:
    from trimtokens.models import (
        CleanStats,
        ExtractedDocument,
        ExtractOptions,
        Section,
    )

    options = ExtractOptions()
    assert options.ocr_languages == "fra+eng"
    assert options.ocr_psm == 6

    stats = CleanStats(original_size_bytes=100, cleaned_size_bytes=20)
    assert stats.reduction_percent == 80.0

    section = Section(header="Test", content="x")
    assert section.header == "Test"

    from pathlib import Path

    doc = ExtractedDocument(source_path=Path("a.pdf"), source_type="pdf")
    assert doc.ocr_used is False


def test_config_paths_resolvable() -> None:
    from trimtokens.config import get_cache_dir, get_config_path, get_home, get_logs_dir

    home = get_home()
    assert home.name in {"trimtokens", ".trimtokens"} or "trimtokens" in str(home).lower()
    assert get_cache_dir() == home / "cache"
    assert get_logs_dir() == home / "logs"
    assert get_config_path() == home / "config.toml"


def test_stats_fallback_tokens() -> None:
    from trimtokens.stats import estimate_tokens

    assert estimate_tokens("hello world") > 0


def test_cli_help_does_not_crash() -> None:
    from typer.testing import CliRunner

    from trimtokens.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
