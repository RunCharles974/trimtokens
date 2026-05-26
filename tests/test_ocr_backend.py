"""Tests pour le backend OCR abstrait (`ocr.backend`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from trimtokens.exceptions import OCRExtractionError
from trimtokens.ocr.backend import (
    OCREngine,
    TesseractBackend,
    get_backend,
    list_backends,
    register_backend,
    unregister_backend,
)

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


class FakeBackend:
    """Backend factice toujours dispo, retourne un texte fixe."""

    name = "fake-test"

    def __init__(self, text: str = "FAKE_OCR_OUTPUT") -> None:
        self._text = text
        self.calls: list[tuple[str, int]] = []

    def is_available(self) -> bool:
        return True

    def extract(self, image: PILImage, *, languages: str, psm: int) -> str:
        self.calls.append((languages, psm))
        return self._text

    def install_hint(self) -> str:
        return "(backend de test — toujours dispo)"


@pytest.fixture
def fake_backend() -> FakeBackend:
    backend = FakeBackend()
    register_backend(backend)
    yield backend
    unregister_backend(backend.name)


def test_tesseract_backend_registered_by_default() -> None:
    backends = list_backends()
    assert "tesseract" in backends


def test_get_backend_returns_tesseract() -> None:
    backend = get_backend("tesseract")
    assert isinstance(backend, TesseractBackend)
    assert backend.name == "tesseract"


def test_get_backend_unknown_raises_ocr_error() -> None:
    with pytest.raises(OCRExtractionError, match="inconnu"):
        get_backend("nonexistent-backend")


def test_tesseract_backend_respects_protocol() -> None:
    backend: OCREngine = TesseractBackend()
    assert isinstance(backend, OCREngine)


def test_fake_backend_respects_protocol() -> None:
    backend: OCREngine = FakeBackend()
    assert isinstance(backend, OCREngine)


def test_register_backend_then_get(fake_backend: FakeBackend) -> None:
    fetched = get_backend("fake-test")
    assert fetched is fake_backend


def test_register_backend_duplicate_raises(fake_backend: FakeBackend) -> None:
    with pytest.raises(ValueError, match="déjà enregistré"):
        register_backend(FakeBackend())


def test_register_backend_replace_overwrites(fake_backend: FakeBackend) -> None:
    new_backend = FakeBackend(text="DIFFERENT")
    register_backend(new_backend, replace=True)
    fetched = get_backend("fake-test")
    assert fetched is new_backend
    assert fetched is not fake_backend


def test_register_backend_empty_name_rejected() -> None:
    class NamelessBackend:
        name = ""

        def is_available(self) -> bool:
            return True

        def extract(self, image: PILImage, *, languages: str, psm: int) -> str:
            return ""

        def install_hint(self) -> str:
            return ""

    with pytest.raises(ValueError, match="sans `name`"):
        register_backend(NamelessBackend())


def test_unregister_backend_idempotent() -> None:
    unregister_backend("nonexistent-backend")  # no raise


def test_extract_options_default_backend() -> None:
    from trimtokens.models import ExtractOptions

    opts = ExtractOptions()
    assert opts.ocr_backend == "tesseract"


def test_image_extractor_uses_registered_backend(
    tmp_path, fake_backend: FakeBackend
) -> None:
    """L'extracteur image route bien vers le backend nommé dans ExtractOptions."""
    from PIL import Image

    from trimtokens.extractors.image import extract
    from trimtokens.models import ExtractOptions

    img_path = tmp_path / "img.png"
    Image.new("RGB", (50, 50), color="white").save(img_path)

    opts = ExtractOptions(ocr_backend="fake-test", use_cache=False)
    doc = extract(img_path, opts)

    assert len(fake_backend.calls) == 1
    assert doc.ocr_used is True
    assert doc.sections[0].content == "FAKE_OCR_OUTPUT"


def test_image_extractor_unknown_backend_raises(tmp_path) -> None:
    from PIL import Image

    from trimtokens.extractors.image import extract
    from trimtokens.models import ExtractOptions

    img_path = tmp_path / "img.png"
    Image.new("RGB", (50, 50), color="white").save(img_path)

    opts = ExtractOptions(ocr_backend="does-not-exist", use_cache=False)
    with pytest.raises(OCRExtractionError, match="inconnu"):
        extract(img_path, opts)
