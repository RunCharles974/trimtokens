"""Service de traitement asynchrone (cf audit §GUI "Gestion threading fragile").

Encapsule l'exécution de `core.process` en arrière-plan et notifie la View via
des callbacks marshallés sur le thread Tk (le caller fournit un `dispatch` qui
fait typiquement `root.after(0, fn, *args)`).

Remplace l'usage direct de `threading.Thread` éparpillé dans la View. Avantages :
- testable sans Tk (mock du dispatcher)
- erreurs propagées via `on_error` au lieu de planter le thread silencieusement
- annulation possible via le flag `_cancel` (future extension)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trimtokens.core import process
from trimtokens.gui.state import FileResult
from trimtokens.models import ExtractOptions, ProcessResult

Dispatcher = Callable[..., None]


@dataclass
class ProcessingCallbacks:
    """Hooks émis par `ProcessingService` au fil du traitement.

    Tous appelés depuis le thread Tk via `dispatch` ; les implémenteurs peuvent
    donc modifier les widgets directement.
    """

    on_progress: Callable[[float, str], None]
    on_file_success: Callable[[Path, ProcessResult, float, FileResult], None]
    on_file_failure: Callable[[Path, Exception, FileResult], None]
    on_complete: Callable[[Path | None, str], None]


class ProcessingService:
    """Lance le pipeline en thread, marshalle les callbacks vers Tk."""

    def __init__(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Demande l'arrêt du batch en cours (best effort, vérifié entre fichiers)."""
        self._cancel.set()

    def start(
        self,
        files: list[Path],
        options: ExtractOptions,
        callbacks: ProcessingCallbacks,
    ) -> threading.Thread:
        """Lance un thread daemon. Retourne le `Thread` pour debug/observation."""
        self._cancel.clear()
        thread = threading.Thread(
            target=self._run,
            args=(files, options, callbacks),
            daemon=True,
            name="trimtokens-processing",
        )
        thread.start()
        return thread

    def _run(
        self,
        files: list[Path],
        options: ExtractOptions,
        callbacks: ProcessingCallbacks,
    ) -> None:
        total = len(files)
        last_output_path: Path | None = None
        last_output_text = ""
        success_count = 0

        for i, file_path in enumerate(files):
            if self._cancel.is_set():
                break

            self._dispatch(
                callbacks.on_progress,
                i / total,
                f"Traitement : {file_path.name} ({i + 1}/{total})",
            )

            try:
                start = time.perf_counter()
                result = process(file_path, options)
                duration = time.perf_counter() - start

                target = file_path.parent / (file_path.stem + ".clean.md")
                target.write_text(result.markdown, encoding="utf-8")
                last_output_path = target
                last_output_text = result.markdown

                entry = _build_success_entry(file_path, target, result, duration)
                success_count += 1
                self._dispatch(callbacks.on_file_success, file_path, result, duration, entry)
            except Exception as exc:
                entry = FileResult(file=file_path.name, target=None, status="✗")
                self._dispatch(callbacks.on_file_failure, file_path, exc, entry)

        self._dispatch(
            callbacks.on_progress,
            1.0,
            f"Terminé : {success_count}/{total} succès",
        )
        self._dispatch(callbacks.on_complete, last_output_path, last_output_text)


def _build_success_entry(
    file_path: Path, target: Path, result: ProcessResult, duration: float
) -> FileResult:
    s = result.stats
    return FileResult(
        file=file_path.name,
        target=target,
        size_before=s.original_size_bytes,
        size_after=s.cleaned_size_bytes,
        tokens_before=s.tokens_input_estimated,
        tokens_after=s.tokens_estimated,
        reduction=s.reduction_percent,
        tokens_reduction=s.tokens_input_reduction_percent,
        duration=duration,
        status="✓",
    )


__all__ = [
    "Dispatcher",
    "ProcessingCallbacks",
    "ProcessingService",
    "_build_success_entry",
]


# Re-export pour rétrocompat des hint Any.
_ = Any
