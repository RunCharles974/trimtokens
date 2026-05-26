"""Parallélisation OCR via ProcessPoolExecutor + barre de progression rich.

Pour PDF multi-pages, on rastérise les pages (PNG bytes) dans le processus principal
puis on dispatch les bytes aux workers — pickling cheap, pas de partage d'objets PIL.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

log = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def default_workers() -> int:
    """Nombre de workers par défaut : `os.cpu_count() - 1`, minimum 1."""
    cpu = os.cpu_count() or 2
    return max(1, cpu - 1)


def parallel_map(
    func: Callable[[T], R],
    items: list[T],
    *,
    workers: int = 0,
    show_progress: bool = True,
    description: str = "OCR",
) -> list[R]:
    """Map parallèle avec progress bar.

    - `workers=0` → `default_workers()`.
    - `workers=1` ou `len(items)==1` → mode séquentiel.
    - Préserve l'ordre des items dans la liste résultat.
    """
    if not items:
        return []
    if workers <= 0:
        workers = default_workers()

    if workers == 1 or len(items) == 1:
        return _sequential_map(func, items, show_progress, description)

    return _parallel_map(func, items, workers, show_progress, description)


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )


def _sequential_map(
    func: Callable[[T], R],
    items: list[T],
    show_progress: bool,
    description: str,
) -> list[R]:
    if not show_progress:
        return [func(item) for item in items]

    results: list[R] = []
    with _make_progress() as progress:
        task = progress.add_task(description, total=len(items))
        for item in items:
            results.append(func(item))
            progress.update(task, advance=1)
    return results


def _parallel_map(
    func: Callable[[T], R],
    items: list[T],
    workers: int,
    show_progress: bool,
    description: str,
) -> list[R]:
    results: list[R | None] = [None] * len(items)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {executor.submit(func, item): idx for idx, item in enumerate(items)}

        if show_progress:
            with _make_progress() as progress:
                task = progress.add_task(description, total=len(items))
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    results[idx] = future.result()
                    progress.update(task, advance=1)
        else:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()

    # mypy : à ce stade tous les résultats sont remplis
    return [r for r in results if r is not None] if False else results  # type: ignore[return-value]
