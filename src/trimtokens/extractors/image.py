"""Extracteur images PNG/JPG/JPEG/WEBP/TIFF/BMP/HEIC via OCR systématique.

Cache SHA-256 sur le contenu binaire + langs + psm. Fallback gracieux si Tesseract
absent : retourne un document vide avec warning.
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

from trimtokens.logging_setup import Events, log_event
from trimtokens.models import ExtractedDocument, ExtractOptions, Section

log = logging.getLogger(__name__)


def extract(path: Path, options: ExtractOptions) -> ExtractedDocument:
    if options.no_ocr:
        log.info("Image '%s' ignorée (no_ocr=True)", path.name)
        return ExtractedDocument(
            source_path=path,
            source_type="image",
            sections=[],
        )

    from trimtokens.ocr.backend import get_backend

    backend = get_backend(options.ocr_backend)
    if not backend.is_available():
        log.warning(
            "Backend OCR '%s' indisponible — image '%s' non traitée.\n%s",
            backend.name,
            path.name,
            backend.install_hint(),
        )
        log_event(
            log,
            Events.OCR_SKIPPED,
            backend=backend.name,
            image=path.name,
            reason="backend_unavailable",
        )
        return ExtractedDocument(
            source_path=path,
            source_type="image",
            sections=[],
        )

    raw_bytes = path.read_bytes()

    from trimtokens.ocr.cache import OCRCache, compute_cache_key

    cache = OCRCache() if options.use_cache else None
    text: str | None = None
    cache_key = ""
    if cache is not None:
        # Clé inclut le backend pour éviter de servir un résultat tesseract à
        # un appel paddleocr (et inversement).
        cache_key = compute_cache_key(
            raw_bytes, f"{backend.name}:{options.ocr_languages}", options.ocr_psm
        )
        text = cache.get(cache_key)
        if text is not None:
            log_event(log, Events.CACHE_HIT, backend=backend.name, image=path.name)

    if text is None:
        log_event(log, Events.OCR_START, backend=backend.name, image=path.name)
        t_ocr_start = time.perf_counter()

        _maybe_register_heif()

        from PIL import Image

        from trimtokens.ocr.preprocess import preprocess

        with Image.open(io.BytesIO(raw_bytes)) as img:
            processed = preprocess(img)
            text = backend.extract(
                processed,
                languages=options.ocr_languages,
                psm=options.ocr_psm,
            )

        if cache is not None and cache_key:
            cache.set(cache_key, text)

        log_event(
            log,
            Events.OCR_COMPLETE,
            backend=backend.name,
            image=path.name,
            chars=len(text),
            duration_ms=round((time.perf_counter() - t_ocr_start) * 1000, 2),
        )

    return ExtractedDocument(
        source_path=path,
        source_type="image",
        sections=[Section(header="Texte extrait (OCR)", content=text)],
        ocr_used=True,
        ocr_pages=[1],
        metadata={"language": options.ocr_languages},
    )


def _maybe_register_heif() -> None:
    """Enregistre le handler HEIC/HEIF si `pillow-heif` est installé."""
    try:
        import pillow_heif  # type: ignore[import-not-found]

        pillow_heif.register_heif_opener()
    except ImportError:
        pass
