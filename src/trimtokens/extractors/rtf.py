"""Extracteur RTF via `striprtf`.

RTF étant un format ASCII étendu, on lit en UTF-8 avec fallback ; `striprtf` gère
les escapes de caractères non-ASCII en interne. Dépendance optionnelle : si le
package n'est pas installé, on lève `MissingDependencyError` au moment de
l'extraction plutôt qu'à l'import du package `trimtokens`.
"""

from __future__ import annotations

from pathlib import Path

try:
    from striprtf.striprtf import rtf_to_text  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - dépendance optionnelle absente
    rtf_to_text = None  # type: ignore[assignment]

from trimtokens.exceptions import MissingDependencyError
from trimtokens.models import ExtractedDocument, ExtractOptions, Section


def extract(path: Path, options: ExtractOptions) -> ExtractedDocument:
    if rtf_to_text is None:
        raise MissingDependencyError(
            "Le package 'striprtf' est requis pour extraire les fichiers .rtf. "
            "Installez-le via : pip install striprtf"
        )
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = rtf_to_text(raw)

    return ExtractedDocument(
        source_path=path,
        source_type="rtf",
        sections=[Section(header="", content=text)],
    )
