"""Exceptions du domaine TrimTokens.

Hiérarchie explicite pour permettre aux appelants (CLI, GUI, API future) de
discriminer finement les erreurs sans recourir à des `except Exception`.
"""

from __future__ import annotations


class TrimTokensError(Exception):
    """Racine de toutes les erreurs métier TrimTokens."""


class UnsupportedFormatError(TrimTokensError, ValueError):
    """Extension de fichier inconnue ou non gérée par le dispatcher.

    Hérite aussi de `ValueError` pour préserver la compat des appelants qui
    attrapaient l'ancien `ValueError` levé par `core._resolve_extractor`.
    """


class MissingDependencyError(TrimTokensError):
    """Dépendance optionnelle absente (striprtf, pytesseract, opencv, …)."""


class ExtractionError(TrimTokensError):
    """Erreur générique pendant l'extraction d'un document."""


class OCRExtractionError(ExtractionError):
    """Erreur spécifique au pipeline OCR (Tesseract indisponible, image corrompue, …)."""


class ConfigError(TrimTokensError):
    """Configuration invalide (TOML mal formé, valeurs hors borne, …)."""


__all__ = [
    "ConfigError",
    "ExtractionError",
    "MissingDependencyError",
    "OCRExtractionError",
    "TrimTokensError",
    "UnsupportedFormatError",
]
