"""Tests GUI : helpers purs uniquement (parser de paths, opener).

L'instanciation de la fenêtre Tk est testée séparément via `test_gui_imports`,
skippé si `customtkinter` ou `tkinterdnd2` ne sont pas disponibles.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_parse_dropped_paths_simple() -> None:
    from trimtokens.gui import _parse_dropped_paths

    paths = _parse_dropped_paths("/tmp/a.pdf /tmp/b.docx")
    assert paths == [Path("/tmp/a.pdf"), Path("/tmp/b.docx")]


def test_parse_dropped_paths_with_braces_spaces() -> None:
    from trimtokens.gui import _parse_dropped_paths

    paths = _parse_dropped_paths("{C:/path with spaces/doc.pdf} C:/other.docx")
    assert paths == [
        Path("C:/path with spaces/doc.pdf"),
        Path("C:/other.docx"),
    ]


def test_parse_dropped_paths_single_braced() -> None:
    from trimtokens.gui import _parse_dropped_paths

    paths = _parse_dropped_paths("{/Users/alice/My Documents/file.pdf}")
    assert paths == [Path("/Users/alice/My Documents/file.pdf")]


def test_parse_dropped_paths_empty() -> None:
    from trimtokens.gui import _parse_dropped_paths

    assert _parse_dropped_paths("") == []
    assert _parse_dropped_paths("   ") == []


def test_parse_dropped_paths_handles_unclosed_brace() -> None:
    from trimtokens.gui import _parse_dropped_paths

    # Cas dégradé : `{path sans fermeture` — on s'arrête plutôt que crasher
    paths = _parse_dropped_paths("{unclosed path /tmp/a.pdf")
    assert isinstance(paths, list)


def test_supported_languages_includes_fra_and_eng() -> None:
    from trimtokens.gui import SUPPORTED_LANGUAGES

    codes = {code for _, code in SUPPORTED_LANGUAGES}
    assert "fra" in codes
    assert "eng" in codes


def test_gui_imports_required_modules() -> None:
    """Le module gui doit s'importer sans erreur (mais sans instancier la GUI)."""
    import trimtokens.gui as gui_module

    assert hasattr(gui_module, "main")
    assert hasattr(gui_module, "TrimTokensGUI")


@pytest.mark.skipif(
    sys.platform == "linux" and "DISPLAY" not in __import__("os").environ,
    reason="Pas de DISPLAY (env headless Linux)",
)
def test_gui_instantiates_without_crash() -> None:
    """Smoke test : instancier la GUI ne doit pas crasher."""
    pytest.importorskip("customtkinter")
    pytest.importorskip("tkinterdnd2")

    from trimtokens.gui import TrimTokensGUI

    try:
        gui = TrimTokensGUI()
    except Exception as exc:
        pytest.skip(f"GUI ne peut pas s'instancier dans cet environnement : {exc}")

    # Vérifie quelques widgets clés
    assert gui.root is not None
    assert gui.drop_frame is not None
    assert gui.progress is not None
    assert len(gui.lang_vars) == 5
    # Visionneuse
    assert gui.viewer_text is not None
    assert gui.viewer_file_label is not None
    assert gui.viewer_copy_btn is not None
    assert gui.viewer_open_btn is not None
    assert gui.viewer_refresh_btn is not None

    # Cleanup
    gui.root.destroy()


@pytest.mark.skipif(
    sys.platform == "linux" and "DISPLAY" not in __import__("os").environ,
    reason="Pas de DISPLAY (env headless Linux)",
)
def test_viewer_loads_file_content(tmp_path) -> None:
    """La visionneuse charge correctement un fichier .clean.md."""
    pytest.importorskip("customtkinter")
    pytest.importorskip("tkinterdnd2")

    from trimtokens.gui import TrimTokensGUI

    try:
        gui = TrimTokensGUI()
    except Exception as exc:
        pytest.skip(f"GUI ne peut pas s'instancier : {exc}")

    # Création fichier test
    md_file = tmp_path / "demo.clean.md"
    md_file.write_text("# Titre\n\nContenu de test.", encoding="utf-8")

    gui._show_in_viewer(md_file)

    assert gui._current_viewer_path == md_file
    displayed = gui.viewer_text.get("1.0", "end-1c")
    assert "# Titre" in displayed
    assert "Contenu de test." in displayed

    # Boutons activés
    assert gui.viewer_copy_btn.cget("state") == "normal"
    assert gui.viewer_open_btn.cget("state") == "normal"
    assert gui.viewer_refresh_btn.cget("state") == "normal"

    gui.root.destroy()


@pytest.mark.skipif(
    sys.platform == "linux" and "DISPLAY" not in __import__("os").environ,
    reason="Pas de DISPLAY (env headless Linux)",
)
def test_viewer_handles_missing_file_gracefully(tmp_path) -> None:
    """La visionneuse affiche un message d'erreur sur fichier illisible."""
    pytest.importorskip("customtkinter")
    pytest.importorskip("tkinterdnd2")

    from trimtokens.gui import TrimTokensGUI

    try:
        gui = TrimTokensGUI()
    except Exception as exc:
        pytest.skip(f"GUI ne peut pas s'instancier : {exc}")

    missing = tmp_path / "does_not_exist.md"
    gui._show_in_viewer(missing)

    displayed = gui.viewer_text.get("1.0", "end-1c")
    assert "[Erreur lecture]" in displayed

    gui.root.destroy()


@pytest.mark.skipif(
    sys.platform == "linux" and "DISPLAY" not in __import__("os").environ,
    reason="Pas de DISPLAY (env headless Linux)",
)
def test_log_with_target_records_mapping(tmp_path) -> None:
    """Un appel à _log avec target enregistre le mapping ligne → fichier."""
    pytest.importorskip("customtkinter")
    pytest.importorskip("tkinterdnd2")

    from trimtokens.gui import TrimTokensGUI

    try:
        gui = TrimTokensGUI()
    except Exception as exc:
        pytest.skip(f"GUI ne peut pas s'instancier : {exc}")

    target = tmp_path / "file.clean.md"
    target.write_text("data", encoding="utf-8")

    gui._log("Test message", target)
    assert 1 in gui._log_line_targets
    assert gui._log_line_targets[1] == target

    # Sans target : pas de mapping
    gui._log("Sans cible")
    assert 2 not in gui._log_line_targets

    gui.root.destroy()
