"""Helpers purs réutilisables par la GUI — testables sans Tk.

Aucune dépendance Tk/customtkinter ici. Logique pure : parsing, formatage,
ouverture explorateur OS.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


# Langues OCR proposées dans la GUI (libellé affiché, code Tesseract).
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("Français", "fra"),
    ("Anglais", "eng"),
    ("Allemand", "deu"),
    ("Espagnol", "spa"),
    ("Italien", "ita"),
]


def _parse_dropped_paths(data: str) -> list[Path]:
    """Parse les chemins droppés depuis l'explorateur.

    Format Windows : `{C:/path with spaces/file.pdf} {C:/other.docx}` (accolades
    autour des paths contenant des espaces). Sur Linux/macOS, séparateur espace
    simple. Cas dégradé (accolade non fermée) : on s'arrête plutôt que crasher.
    """
    paths: list[Path] = []
    i = 0
    while i < len(data):
        ch = data[i]
        if ch == "{":
            try:
                end = data.index("}", i)
                paths.append(Path(data[i + 1 : end]))
                i = end + 1
            except ValueError:
                break
        elif ch.isspace():
            i += 1
        else:
            start = i
            while i < len(data) and not data[i].isspace():
                i += 1
            paths.append(Path(data[start:i]))
    return paths


def _format_bytes(n: int) -> str:
    """Formate des octets en unité lisible (o/Ko/Mo/Go/To)."""
    value = float(n)
    for unit in ("o", "Ko", "Mo", "Go"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} To"


def _format_count(n: int) -> str:
    """Formate un grand nombre avec espace fine comme séparateur de milliers."""
    return f"{n:,}".replace(",", " ")


def _open_in_explorer(path: Path) -> None:
    """Ouvre `path` (fichier ou dossier) avec l'explorateur natif de l'OS."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:
        log.warning("Impossible d'ouvrir %s : %s", path, exc)


__all__ = [
    "SUPPORTED_LANGUAGES",
    "_format_bytes",
    "_format_count",
    "_open_in_explorer",
    "_parse_dropped_paths",
]
