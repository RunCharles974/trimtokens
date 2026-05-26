"""Tests Phase 3 : cache OCR + engine availability + preprocess pipeline.

Les tests OCR de bout-en-bout nécessitent Tesseract installé : ils sont automatiquement
skippés via `pytest.skip(...)` si `is_tesseract_available()` retourne False.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trimtokens.ocr.cache import OCRCache, compute_cache_key, compute_file_cache_key
from trimtokens.ocr.engine import is_tesseract_available

# --- Cache -------------------------------------------------------------------


def test_compute_cache_key_deterministic() -> None:
    k1 = compute_cache_key(b"abc", "fra+eng", 6)
    k2 = compute_cache_key(b"abc", "fra+eng", 6)
    assert k1 == k2
    assert len(k1) == 64  # SHA-256 hex


def test_compute_cache_key_differs_per_payload() -> None:
    assert compute_cache_key(b"abc", "fra", 6) != compute_cache_key(b"abd", "fra", 6)


def test_compute_cache_key_differs_per_language() -> None:
    assert compute_cache_key(b"abc", "fra", 6) != compute_cache_key(b"abc", "eng", 6)


def test_compute_cache_key_differs_per_psm() -> None:
    assert compute_cache_key(b"abc", "fra", 6) != compute_cache_key(b"abc", "fra", 11)


def test_compute_file_cache_key_reads_file(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello")
    k = compute_file_cache_key(f, "fra", 6)
    expected = compute_cache_key(b"hello", "fra", 6)
    assert k == expected


def test_ocr_cache_set_and_get(tmp_path: Path) -> None:
    cache = OCRCache(cache_dir=tmp_path)
    cache.set("abc123", "texte OCR résultat")
    assert cache.get("abc123") == "texte OCR résultat"


def test_ocr_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = OCRCache(cache_dir=tmp_path)
    assert cache.get("inexistant") is None


def test_ocr_cache_creates_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / "deep" / "nested" / "cache"
    OCRCache(cache_dir=cache_dir)
    assert cache_dir.is_dir()


def test_ocr_cache_preserves_unicode(tmp_path: Path) -> None:
    cache = OCRCache(cache_dir=tmp_path)
    cache.set("k1", "café — éléphant 中文")
    assert cache.get("k1") == "café — éléphant 中文"


# --- Engine ------------------------------------------------------------------


def test_is_tesseract_available_returns_bool() -> None:
    result = is_tesseract_available()
    assert isinstance(result, bool)


def test_ocr_pil_image_without_tesseract_returns_empty() -> None:
    """Si Tesseract absent, ocr_pil_image retourne chaîne vide (fallback gracieux)."""
    if is_tesseract_available():
        pytest.skip("Tesseract installé — test fallback non applicable")
    from PIL import Image

    from trimtokens.ocr.engine import ocr_pil_image

    img = Image.new("L", (50, 50), 255)
    assert ocr_pil_image(img) == ""


# --- Preprocess --------------------------------------------------------------


def test_preprocess_returns_grayscale_or_binary() -> None:
    from PIL import Image

    from trimtokens.ocr.preprocess import preprocess

    img = Image.new("RGB", (200, 200), (255, 255, 255))
    out = preprocess(img)
    assert out.mode in {"L", "1"}


def test_preprocess_upscales_low_dpi_image() -> None:
    from PIL import Image

    from trimtokens.ocr.preprocess import upscale_if_needed

    img = Image.new("L", (100, 100), 255)
    img.info["dpi"] = (72, 72)
    out = upscale_if_needed(img, min_dpi=300)
    assert out.width > img.width
    assert out.height > img.height


def test_preprocess_skips_upscale_if_dpi_sufficient() -> None:
    from PIL import Image

    from trimtokens.ocr.preprocess import upscale_if_needed

    img = Image.new("L", (100, 100), 255)
    img.info["dpi"] = (300, 300)
    out = upscale_if_needed(img, min_dpi=300)
    assert out.size == img.size


def test_to_grayscale_idempotent() -> None:
    from PIL import Image

    from trimtokens.ocr.preprocess import to_grayscale

    img = Image.new("L", (50, 50), 128)
    out = to_grayscale(img)
    assert out.mode == "L"


def test_binarize_returns_image_with_only_extreme_values() -> None:
    from PIL import Image

    from trimtokens.ocr.preprocess import binarize

    img = Image.new("L", (50, 50), 128)
    out = binarize(img)
    pixels = set(out.getdata())
    # Après binarisation, on attend au plus deux valeurs (0 et 255)
    assert pixels.issubset({0, 255}) or pixels.issubset({0, 1, 255})


# --- PDF extractor -----------------------------------------------------------


def test_pdf_extractor_native_text_no_ocr_needed(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")

    from trimtokens.extractors.pdf import extract
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "native.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Bonjour, ceci est un document PDF avec du texte natif extractible facilement.",
    )
    doc.save(str(pdf_path))
    doc.close()

    result = extract(pdf_path, ExtractOptions(no_ocr=True))
    assert result.source_type == "pdf"
    assert result.ocr_used is False
    assert result.ocr_pages == []
    assert len(result.sections) >= 1
    assert any("Bonjour" in s.content for s in result.sections)
    assert result.sections[0].header == "Page 1"


def test_pdf_extractor_multi_page(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")

    from trimtokens.extractors.pdf import extract
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "multi.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"Page numero {i + 1}. Contenu unique pour page {i + 1}. " * 5,
        )
    doc.save(str(pdf_path))
    doc.close()

    result = extract(pdf_path, ExtractOptions(no_ocr=True))
    assert len(result.sections) == 3
    assert result.ocr_used is False
    headers = [s.header for s in result.sections]
    assert headers == ["Page 1", "Page 2", "Page 3"]


def test_pdf_extractor_force_ocr_without_tesseract_falls_back(tmp_path: Path) -> None:
    """force_ocr=True sans Tesseract → warning + texte natif conservé."""
    if is_tesseract_available():
        pytest.skip("Tesseract installé — test fallback non applicable")

    fitz = pytest.importorskip("fitz")

    from trimtokens.extractors.pdf import extract
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "force.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Texte natif présent ici, suffisamment long pour passer.")
    doc.save(str(pdf_path))
    doc.close()

    result = extract(pdf_path, ExtractOptions(force_ocr=True))
    # Pas d'OCR utilisable → ocr_used False, texte natif conservé
    assert result.ocr_used is False
    assert any("Texte natif présent" in s.content for s in result.sections)


# --- Image extractor ---------------------------------------------------------


def test_image_extractor_no_ocr_returns_empty_sections(tmp_path: Path) -> None:
    from PIL import Image

    from trimtokens.extractors.image import extract
    from trimtokens.models import ExtractOptions

    img_path = tmp_path / "test.png"
    Image.new("RGB", (100, 100), (255, 255, 255)).save(img_path)

    result = extract(img_path, ExtractOptions(no_ocr=True))
    assert result.source_type == "image"
    assert result.sections == []


def test_image_extractor_without_tesseract_returns_empty(tmp_path: Path) -> None:
    if is_tesseract_available():
        pytest.skip("Tesseract installé — test fallback non applicable")

    from PIL import Image

    from trimtokens.extractors.image import extract
    from trimtokens.models import ExtractOptions

    img_path = tmp_path / "test.png"
    Image.new("RGB", (100, 100), (255, 255, 255)).save(img_path)

    result = extract(img_path, ExtractOptions())
    assert result.sections == []


# --- Core dispatch -----------------------------------------------------------


def test_core_dispatches_pdf(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")

    from trimtokens.core import process
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "core.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Test core dispatch sur PDF natif.")
    doc.save(str(pdf_path))
    doc.close()

    result = process(pdf_path, ExtractOptions(no_ocr=True))
    assert result.document.source_type == "pdf"
    assert "Test core dispatch" in result.markdown
    assert "type: pdf" in result.markdown


def test_core_dispatches_image_extension(tmp_path: Path) -> None:
    from PIL import Image

    from trimtokens.core import process
    from trimtokens.models import ExtractOptions

    img_path = tmp_path / "test.png"
    Image.new("RGB", (50, 50), (255, 255, 255)).save(img_path)

    result = process(img_path, ExtractOptions(no_ocr=True))
    assert result.document.source_type == "image"
