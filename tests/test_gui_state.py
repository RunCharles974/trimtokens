"""Tests pour les nouvelles couches MVVM GUI : `state` et `services`.

Aucune dépendance Tk requise — ces modules sont testables headless. Le seul
contact avec la View réelle est le `dispatch` callback que `ProcessingService`
invoque ; on injecte un faux dispatcher qui exécute synchroniquement.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from trimtokens.gui.services import (
    ProcessingCallbacks,
    ProcessingService,
    _build_success_entry,
)
from trimtokens.gui.state import AppState, FileResult
from trimtokens.models import ExtractOptions

# --- AppState -------------------------------------------------------------


def test_appstate_defaults() -> None:
    state = AppState()
    assert state.processing is False
    assert state.output_dir is None
    assert state.results == []
    assert state.log_line_targets == {}
    assert state.current_viewer_path is None


def test_appstate_reset_batch_clears_results_only() -> None:
    state = AppState()
    state.processing = True
    state.results.append(FileResult(file="a.pdf", target=None))
    state.log_line_targets[3] = Path("/tmp/x.md")
    state.output_dir = Path("/tmp")

    state.reset_batch()

    assert state.results == []
    # log_line_targets et output_dir conservés (UX : double-clic sur ancienne
    # ligne reste fonctionnel après un nouveau batch).
    assert state.log_line_targets == {3: Path("/tmp/x.md")}
    assert state.output_dir == Path("/tmp")
    assert state.processing is True  # reset_batch ne touche pas au flag


# --- FileResult -----------------------------------------------------------


def test_fileresult_defaults() -> None:
    fr = FileResult(file="x.pdf", target=Path("/tmp/x.clean.md"))
    assert fr.file == "x.pdf"
    assert fr.target == Path("/tmp/x.clean.md")
    assert fr.size_before == 0
    assert fr.status == "✓"


def test_fileresult_dict_compat() -> None:
    """Compat lecture clé style dict (legacy code path éventuel)."""
    fr = FileResult(file="a", target=None, size_before=100, status="✓")
    assert fr["file"] == "a"
    assert fr["size_before"] == 100
    assert fr["status"] == "✓"


# --- ProcessingService ---------------------------------------------------


def _sync_dispatch(func, *args):
    """Dispatcher fake qui exécute synchroniquement (au lieu de root.after)."""
    func(*args)


def test_processing_service_success(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("hello world", encoding="utf-8")

    progress_calls: list[tuple[float, str]] = []
    success_calls: list[FileResult] = []
    failure_calls: list[tuple[Path, Exception]] = []
    completes: list[tuple[Path | None, str]] = []
    done = threading.Event()

    def on_progress(value: float, status: str) -> None:
        progress_calls.append((value, status))

    def on_success(file_path, result, duration, entry) -> None:
        success_calls.append(entry)

    def on_failure(file_path, exc, entry) -> None:
        failure_calls.append((file_path, exc))

    def on_complete(last_path, last_text) -> None:
        completes.append((last_path, last_text))
        done.set()

    service = ProcessingService(dispatch=_sync_dispatch)
    callbacks = ProcessingCallbacks(
        on_progress=on_progress,
        on_file_success=on_success,
        on_file_failure=on_failure,
        on_complete=on_complete,
    )

    thread = service.start([src], ExtractOptions(), callbacks)
    thread.join(timeout=10)

    assert done.wait(timeout=2)
    assert len(success_calls) == 1
    assert success_calls[0].status == "✓"
    assert success_calls[0].file == "doc.txt"
    assert failure_calls == []
    # Progress émis au moins 2 fois (1 par fichier + final 1.0)
    assert any(value == 1.0 for value, _ in progress_calls)
    # Complete émis avec un last_path non-None
    assert completes[0][0] is not None
    assert "Terminé" in progress_calls[-1][1]


def test_processing_service_failure(tmp_path: Path) -> None:
    """Fichier au format non supporté → UnsupportedFormatError capturé."""
    src = tmp_path / "weird.xyz"
    src.write_text("data", encoding="utf-8")

    success_calls: list[FileResult] = []
    failure_calls: list[tuple[Path, Exception]] = []
    done = threading.Event()

    def on_complete(*_args) -> None:
        done.set()

    callbacks = ProcessingCallbacks(
        on_progress=lambda *_: None,
        on_file_success=lambda *_args: success_calls.append(_args[3]),
        on_file_failure=lambda fp, exc, entry: failure_calls.append((fp, exc)),
        on_complete=on_complete,
    )

    service = ProcessingService(dispatch=_sync_dispatch)
    service.start([src], ExtractOptions(), callbacks)
    assert done.wait(timeout=5)

    assert success_calls == []
    assert len(failure_calls) == 1
    assert "non supporté" in str(failure_calls[0][1])


def test_processing_service_cancel_between_files(tmp_path: Path) -> None:
    """`cancel()` arrête la boucle avant le fichier suivant (best effort)."""
    src1 = tmp_path / "a.txt"
    src1.write_text("hello", encoding="utf-8")
    src2 = tmp_path / "b.txt"
    src2.write_text("world", encoding="utf-8")

    processed_files: list[str] = []
    done = threading.Event()

    def on_success(file_path, result, duration, entry) -> None:
        processed_files.append(entry.file)
        # Annule après le premier fichier traité ; le second ne doit pas l'être.
        service.cancel()

    def on_complete(*_args) -> None:
        done.set()

    service = ProcessingService(dispatch=_sync_dispatch)
    callbacks = ProcessingCallbacks(
        on_progress=lambda *_: None,
        on_file_success=on_success,
        on_file_failure=lambda *_: None,
        on_complete=on_complete,
    )
    service.start([src1, src2], ExtractOptions(), callbacks)

    assert done.wait(timeout=5)
    assert processed_files == ["a.txt"]


def test_build_success_entry_maps_stats(tmp_path: Path) -> None:
    from trimtokens.core import process

    src = tmp_path / "doc.txt"
    src.write_text("hello   world", encoding="utf-8")
    target = tmp_path / "doc.clean.md"
    result = process(src)

    entry = _build_success_entry(src, target, result, duration=0.42)
    assert entry.file == "doc.txt"
    assert entry.target == target
    assert entry.size_before == result.stats.original_size_bytes
    assert entry.size_after == result.stats.cleaned_size_bytes
    assert entry.tokens_before == result.stats.tokens_input_estimated
    assert entry.tokens_after == result.stats.tokens_estimated
    assert entry.duration == pytest.approx(0.42)
    assert entry.status == "✓"


# --- Compat layer TrimTokensGUI -------------------------------------------


def test_gui_module_exports_public_names() -> None:
    """Surface API historique préservée après split en sous-package."""
    import trimtokens.gui as gui_module

    expected = {
        "TrimTokensGUI",
        "main",
        "_parse_dropped_paths",
        "_format_bytes",
        "_format_count",
        "_open_in_explorer",
        "SUPPORTED_LANGUAGES",
    }
    for name in expected:
        assert hasattr(gui_module, name), f"Missing export: {name}"


def test_format_bytes_units() -> None:
    from trimtokens.gui import _format_bytes

    assert _format_bytes(0) == "0.0 o"
    assert _format_bytes(512) == "512.0 o"
    assert _format_bytes(2048) == "2.0 Ko"
    assert _format_bytes(5 * 1024 * 1024) == "5.0 Mo"


def test_format_count_thousands_separator() -> None:
    from trimtokens.gui import _format_count

    assert _format_count(1234) == "1 234"
    assert _format_count(1_234_567) == "1 234 567"
    assert _format_count(0) == "0"


# Suppress unused import warning when test collected without execution
_ = time
