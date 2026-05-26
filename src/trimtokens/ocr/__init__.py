"""Module OCR : engine Tesseract, préprocessing OpenCV, cache disque, parallélisation.

Backend OCR pluggable via `OCREngine` Protocol (cf `backend.py`). Le backend
"tesseract" est enregistré par défaut ; d'autres moteurs (EasyOCR, PaddleOCR…)
peuvent s'enregistrer via `register_backend()`.
"""

from __future__ import annotations

from trimtokens.ocr.backend import (
    OCREngine,
    TesseractBackend,
    get_backend,
    list_backends,
    register_backend,
    unregister_backend,
)
from trimtokens.ocr.cache import OCRCache, compute_cache_key, compute_file_cache_key
from trimtokens.ocr.engine import (
    get_tesseract_install_hint,
    is_tesseract_available,
    ocr_file,
    ocr_pil_image,
)
from trimtokens.ocr.parallel import default_workers, parallel_map
from trimtokens.ocr.preprocess import preprocess

__all__ = [
    "OCRCache",
    "OCREngine",
    "TesseractBackend",
    "compute_cache_key",
    "compute_file_cache_key",
    "default_workers",
    "get_backend",
    "get_tesseract_install_hint",
    "is_tesseract_available",
    "list_backends",
    "ocr_file",
    "ocr_pil_image",
    "parallel_map",
    "preprocess",
    "register_backend",
    "unregister_backend",
]
