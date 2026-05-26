"""Tests CLI typer."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from trimtokens import __version__
from trimtokens.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "trimtokens" in result.stdout.lower()


def test_cli_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout or "usage" in result.stdout


def test_cli_processes_txt_file_default_output(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello world.\n\nLine 2.", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--quiet"])
    assert result.exit_code == 0

    target = tmp_path / "doc.clean.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "Hello world." in content
    assert "---\nsource:" in content


def test_cli_format_txt(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello world.", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--format", "txt", "--quiet"])
    assert result.exit_code == 0

    target = tmp_path / "doc.clean.txt"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "Hello world." in content
    # Pas de front-matter YAML pour format txt
    assert not content.startswith("---\n")


def test_cli_format_json(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Bonjour le monde.", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--format", "json", "--quiet"])
    assert result.exit_code == 0

    target = tmp_path / "doc.clean.json"
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["source"] == "doc.txt"
    assert data["type"] == "txt"
    assert "stats" in data
    assert isinstance(data["sections"], list)


def test_cli_invalid_format_rejected(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("test", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--format", "xml"])
    assert result.exit_code != 0


def test_cli_no_ocr_and_force_ocr_mutually_exclusive(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("test", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--no-ocr", "--force-ocr"])
    assert result.exit_code != 0


def test_cli_quiet_suppresses_stats(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello world.", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--quiet"])
    assert result.exit_code == 0
    # Pas de table dans stdout en mode quiet
    assert "Métrique" not in result.stdout


def test_cli_stats_shown_by_default(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello world.", encoding="utf-8")

    result = runner.invoke(app, [str(src)])
    assert result.exit_code == 0
    # Table affichée
    assert "Métrique" in result.stdout or "Avant" in result.stdout


def test_cli_stdout_writes_to_stdout(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Bonjour!", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--stdout", "--quiet"])
    assert result.exit_code == 0
    assert "Bonjour!" in result.stdout

    # Aucun fichier .clean.md créé
    assert not (tmp_path / "doc.clean.md").exists()


def test_cli_out_directory(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello.", encoding="utf-8")
    out_dir = tmp_path / "output"

    result = runner.invoke(app, [str(src), "--out", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    assert (out_dir / "doc.clean.md").exists()


def test_cli_out_directory_created_if_missing(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Hello.", encoding="utf-8")
    out_dir = tmp_path / "deep" / "nested" / "output"

    result = runner.invoke(app, [str(src), "--out", str(out_dir), "--quiet"])
    assert result.exit_code == 0
    assert out_dir.is_dir()
    assert (out_dir / "doc.clean.md").exists()


def test_cli_recursive_directory(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("File A", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("File B", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [str(tmp_path), "--recursive", "--out", str(out_dir), "--quiet"],
    )
    assert result.exit_code == 0

    outputs = sorted(p.name for p in out_dir.glob("*.clean.md"))
    assert "a.clean.md" in outputs
    assert "b.clean.md" in outputs


def test_cli_non_recursive_skips_subdirs(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("File A", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("File B", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [str(tmp_path), "--out", str(out_dir), "--quiet"],
    )
    assert result.exit_code == 0

    outputs = sorted(p.name for p in out_dir.glob("*.clean.md"))
    assert outputs == ["a.clean.md"]


def test_cli_nonexistent_path_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path / "does_not_exist.txt")])
    assert result.exit_code == 1


def test_cli_unsupported_format_exits_with_error(tmp_path: Path) -> None:
    src = tmp_path / "doc.xyz"
    src.write_text("data", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--quiet"])
    # Aucun extracteur trouvé → erreur loggée + exit 1
    assert result.exit_code == 1


def test_cli_aggressive_flag_accepted(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("para X\n\npara Y\n\npara X", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--aggressive", "--quiet"])
    assert result.exit_code == 0


def test_cli_max_chars_truncates(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    long_text = "abc " * 1000
    src.write_text(long_text, encoding="utf-8")

    result = runner.invoke(app, [str(src), "--max-chars", "100", "--quiet"])
    assert result.exit_code == 0

    target = tmp_path / "doc.clean.md"
    content = target.read_text(encoding="utf-8")
    assert len(content) <= 100


def test_cli_workers_option_accepted(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("test", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--workers", "2", "--quiet"])
    assert result.exit_code == 0


def test_cli_psm_option_accepted(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("test", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--ocr-psm", "11", "--quiet"])
    assert result.exit_code == 0


def test_cli_psm_out_of_range_rejected(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("test", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--ocr-psm", "99"])
    assert result.exit_code != 0
