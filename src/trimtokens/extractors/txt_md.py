"""Extracteur TXT / MD : décode le fichier en UTF-8 (avec détection d'encodage) et
retourne une unique section sans transformation structurelle.

Le pipeline de nettoyage commun se charge ensuite des espaces et caractères parasites.
"""

from __future__ import annotations

from pathlib import Path

from trimtokens.extractors._encoding import detect_encoding
from trimtokens.models import ExtractedDocument, ExtractOptions, Section


def extract(path: Path, options: ExtractOptions) -> ExtractedDocument:
    raw = path.read_bytes()
    encoding = detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")

    ext = path.suffix.lower()
    source_type = "markdown" if ext in {".md", ".markdown"} else "txt"

    return ExtractedDocument(
        source_path=path,
        source_type=source_type,
        title=None,
        sections=[Section(header="", content=text)],
        metadata={"encoding": encoding},
    )
