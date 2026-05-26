"""Tests multiprocessing OCR : `_resolve_ocr_workers`, `_ocr_worker`, `parallel_map`."""

from __future__ import annotations

from pathlib import Path

import pytest

from trimtokens.ocr.parallel import default_workers, parallel_map

# --- _resolve_ocr_workers ------------------------------------------------


def test_resolve_workers_single_item_always_one() -> None:
    from trimtokens.extractors.pdf import _resolve_ocr_workers

    assert _resolve_ocr_workers(0, 1) == 1
    assert _resolve_ocr_workers(4, 1) == 1
    assert _resolve_ocr_workers(0, 0) == 1


def test_resolve_workers_zero_means_auto() -> None:
    from trimtokens.extractors.pdf import _resolve_ocr_workers

    result = _resolve_ocr_workers(0, 10)
    assert result == min(default_workers(), 10)


def test_resolve_workers_explicit_value() -> None:
    from trimtokens.extractors.pdf import _resolve_ocr_workers

    assert _resolve_ocr_workers(3, 10) == 3
    assert _resolve_ocr_workers(8, 4) == 4  # borné par num_items


def test_resolve_workers_one_forces_sequential() -> None:
    from trimtokens.extractors.pdf import _resolve_ocr_workers

    assert _resolve_ocr_workers(1, 10) == 1


# --- parallel_map ---------------------------------------------------------


def _square(x: int) -> int:
    """Worker top-level (picklable) pour les tests parallel_map."""
    return x * x


def test_parallel_map_preserves_order_sequential() -> None:
    items = [1, 2, 3, 4, 5]
    result = parallel_map(_square, items, workers=1, show_progress=False)
    assert result == [1, 4, 9, 16, 25]


def test_parallel_map_preserves_order_parallel() -> None:
    items = list(range(10))
    result = parallel_map(_square, items, workers=2, show_progress=False)
    assert result == [x * x for x in items]


def test_parallel_map_empty_list_returns_empty() -> None:
    assert parallel_map(_square, [], workers=4, show_progress=False) == []


def test_parallel_map_single_item_sequential() -> None:
    assert parallel_map(_square, [7], workers=4, show_progress=False) == [49]


# --- _ocr_worker (picklable, FakeBackend en sub-process) -----------------


def test_ocr_worker_with_registered_backend_sequential(tmp_path: Path) -> None:
    """`_ocr_worker` route correctement vers le backend nommé.

    Test en mode séquentiel (workers=1) — la version multi-process est testée
    indirectement par `test_pdf_extraction_parallel_smoke` qui simule un PDF.
    """
    import io

    from PIL import Image

    from trimtokens.extractors.pdf import _ocr_worker
    from trimtokens.ocr.backend import register_backend, unregister_backend

    class StubBackend:
        name = "stub-seq"

        def is_available(self) -> bool:
            return True

        def extract(self, image, *, languages: str, psm: int) -> str:
            return f"STUB({languages}/{psm})"

        def install_hint(self) -> str:
            return ""

    register_backend(StubBackend())
    try:
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), color="white").save(buf, format="PNG")
        image_bytes = buf.getvalue()

        result = _ocr_worker((image_bytes, 6, "stub-seq", "fra"))
        assert result == "STUB(fra/6)"
    finally:
        unregister_backend("stub-seq")


# --- ExtractOptions.workers consommé par _ocr_page_images ----------------


def test_extract_options_workers_default_is_zero() -> None:
    from trimtokens.models import ExtractOptions

    assert ExtractOptions().workers == 0  # auto


def test_ocr_page_images_sequential_workers_one() -> None:
    """workers=1 → exécution séquentielle in-process (pas de spawn)."""
    import io

    from PIL import Image

    from trimtokens.extractors.pdf import _ocr_page_images
    from trimtokens.models import ExtractOptions
    from trimtokens.ocr.backend import register_backend, unregister_backend

    class CountingBackend:
        name = "counting-seq"

        def __init__(self) -> None:
            self.calls = 0

        def is_available(self) -> bool:
            return True

        def extract(self, image, *, languages: str, psm: int) -> str:
            self.calls += 1
            return f"page-{self.calls}-psm-{psm}"

        def install_hint(self) -> str:
            return ""

    backend = CountingBackend()
    register_backend(backend)
    try:
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), color="white").save(buf, format="PNG")
        image_bytes = buf.getvalue()

        specs = [(image_bytes, 6), (image_bytes, 11), (image_bytes, 6)]
        opts = ExtractOptions(workers=1, ocr_backend="counting-seq")

        results = _ocr_page_images(specs, opts, backend)

        # En séquentiel l'instance backend reçoit bien les appels (pas de pickling).
        assert backend.calls == 3
        assert len(results) == 3
        assert all("page-" in r for r in results)
        # Ordre conservé
        assert "psm-11" in results[1]
    finally:
        unregister_backend("counting-seq")


def test_ocr_page_images_empty_returns_empty() -> None:
    from trimtokens.extractors.pdf import _ocr_page_images
    from trimtokens.models import ExtractOptions
    from trimtokens.ocr.backend import get_backend

    backend = get_backend("tesseract")
    assert _ocr_page_images([], ExtractOptions(), backend) == []


@pytest.mark.skipif(
    default_workers() < 2,
    reason="CPU mono-cœur — pas de gain à tester le parallélisme",
)
def test_ocr_page_images_parallel_path_invoked() -> None:
    """workers=2 + 4 pages → route multiprocessing (résolution > 1)."""
    from trimtokens.extractors.pdf import _resolve_ocr_workers

    assert _resolve_ocr_workers(2, 4) == 2  # confirme branchement parallèle
