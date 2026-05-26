"""Helpers partagés pour détection d'encodage des fichiers texte/CSV."""

from __future__ import annotations


def detect_encoding(data: bytes) -> str:
    """Détecte l'encodage d'un bloc d'octets.

    Ordre :
    1. BOM UTF-8 → `utf-8-sig`
    2. BOM UTF-16 LE/BE → `utf-16`
    3. Tentative `utf-8` strict
    4. Fallback `chardet`
    5. Fallback ultime `latin-1`
    """
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return "utf-16"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        import chardet

        result = chardet.detect(data)
        encoding = result.get("encoding")
        if encoding:
            return encoding
    except Exception:
        pass
    return "latin-1"
