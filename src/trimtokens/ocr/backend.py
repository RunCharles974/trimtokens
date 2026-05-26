"""Backend OCR abstrait (cf audit §OCR "Pas de backend abstrait").

Le Protocol `OCREngine` permet d'enficher d'autres moteurs (EasyOCR, PaddleOCR,
OCR GPU, OCR cloud) sans modifier les call sites dans `extractors/`.

Registry simple : `register_backend(name, engine)`, `get_backend(name)`.
`TesseractBackend` est enregistré par défaut sous le nom `"tesseract"`.

Usage côté extracteur :

    backend = get_backend(options.ocr_backend)
    if backend.is_available():
        text = backend.extract(image, languages=..., psm=...)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from trimtokens.exceptions import OCRExtractionError

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

log = logging.getLogger(__name__)


@runtime_checkable
class OCREngine(Protocol):
    """Contrat d'un moteur OCR plug-and-play.

    Implémentations attendues : `is_available()` (vérif binaire/lib), `extract()`
    (transcription d'une image préprocessée), `name` (identifiant registry).
    """

    name: str

    def is_available(self) -> bool: ...

    def extract(self, image: PILImage, *, languages: str, psm: int) -> str: ...

    def install_hint(self) -> str: ...


# --- Implémentation Tesseract (défaut) -----------------------------------


class TesseractBackend:
    """Backend Tesseract via `pytesseract` (implémentation historique).

    Délègue à `ocr.engine` pour préserver la détection auto du binaire et la
    config `TESSDATA_PREFIX`.
    """

    name = "tesseract"

    def is_available(self) -> bool:
        from trimtokens.ocr.engine import is_tesseract_available

        return is_tesseract_available()

    def extract(self, image: PILImage, *, languages: str, psm: int) -> str:
        from trimtokens.ocr.engine import ocr_pil_image

        return ocr_pil_image(image, languages=languages, psm=psm)

    def install_hint(self) -> str:
        from trimtokens.ocr.engine import get_tesseract_install_hint

        return get_tesseract_install_hint()


# --- Registry ------------------------------------------------------------


_BACKENDS: dict[str, OCREngine] = {}


def register_backend(backend: OCREngine, *, replace: bool = False) -> None:
    """Enregistre `backend` sous son `name`. Lève si déjà présent (sauf `replace=True`)."""
    name = backend.name
    if not name:
        raise ValueError("Backend OCR sans `name` non enregistrable.")
    if name in _BACKENDS and not replace:
        raise ValueError(
            f"Backend OCR '{name}' déjà enregistré. Passez replace=True pour écraser."
        )
    _BACKENDS[name] = backend
    log.debug("Backend OCR enregistré : %s", name)


def unregister_backend(name: str) -> None:
    """Retire un backend du registry (no-op si absent). Utile pour les tests."""
    _BACKENDS.pop(name, None)


def get_backend(name: str) -> OCREngine:
    """Retourne le backend nommé. Lève `OCRExtractionError` si inconnu."""
    backend = _BACKENDS.get(name)
    if backend is None:
        available = ", ".join(sorted(_BACKENDS)) or "(aucun)"
        raise OCRExtractionError(
            f"Backend OCR '{name}' inconnu. Backends disponibles : {available}."
        )
    return backend


def list_backends() -> list[str]:
    """Liste des noms de backends enregistrés (ordre non garanti)."""
    return sorted(_BACKENDS)


# Enregistrement par défaut au chargement du module.
register_backend(TesseractBackend())


__all__ = [
    "OCREngine",
    "TesseractBackend",
    "get_backend",
    "list_backends",
    "register_backend",
    "unregister_backend",
]
