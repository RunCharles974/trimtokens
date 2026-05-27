"""Extracteur PDF via pymupdf avec routing OCR page-par-page.

Heuristique de déclenchement OCR :
- `force_ocr=True` → OCR systématique
- `no_ocr=True` → aucune OCR
- Sinon : OCR uniquement sur pages avec < MIN_NATIVE_CHARS_PER_PAGE caractères extractibles

Cache OCR : SHA-256(image_bytes + langs + psm) → résultat texte sur disque.
"""

from __future__ import annotations

import contextlib
import io
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import fitz  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - dépendance optionnelle absente
    fitz = None  # type: ignore[assignment]

from trimtokens.cleaners.heuristics import analyze_pages, filter_pages
from trimtokens.cleaners.page_merge import mark_continuations
from trimtokens.cleaners.pipeline import strip_recurring_headers_footers
from trimtokens.exceptions import MissingDependencyError
from trimtokens.logging_setup import Events, log_event
from trimtokens.models import ExtractedDocument, ExtractOptions, Section

if TYPE_CHECKING:
    from trimtokens.ocr.backend import OCREngine

log = logging.getLogger(__name__)

# Valeurs par défaut historiques — conservées pour compat des appelants qui
# importent ces constantes ou utilisent `detect_image_based()` sans options.
# Les valeurs effectives au runtime proviennent de `ExtractOptions` (voir models.py).
MIN_NATIVE_CHARS_PER_PAGE = 50
DEFAULT_OCR_DPI = 300

# Seuils détection PDF "image-based" (défauts) :
# - < 100 chars natifs / page en moyenne
# - >= 2 images embarquées / page en moyenne
# - >= 3 pages (sinon échantillon trop petit)
IMAGE_BASED_MAX_CHARS_PER_PAGE = 100
IMAGE_BASED_MIN_IMAGES_PER_PAGE = 2
IMAGE_BASED_MIN_PAGES = 3


def detect_image_based(
    pages_native: list[str],
    total_images: int,
    *,
    max_chars_per_page: int = IMAGE_BASED_MAX_CHARS_PER_PAGE,
    min_images_per_page: int = IMAGE_BASED_MIN_IMAGES_PER_PAGE,
    min_pages: int = IMAGE_BASED_MIN_PAGES,
) -> tuple[bool, dict[str, float]]:
    """Détecte si un PDF est `image-based` (contenu dans images, pas en texte natif).

    Retourne (is_image_based, metrics_dict). `metrics_dict` toujours rempli
    pour permettre l'affichage du diagnostic même en cas de négatif. Seuils
    surchargés via kwargs (alimentés par `ExtractOptions` dans `extract()`).
    """
    page_count = len(pages_native)
    if page_count == 0:
        return False, {"page_count": 0}

    total_chars = sum(len(p.strip()) for p in pages_native)
    avg_chars = total_chars / page_count
    avg_images = total_images / page_count

    metrics = {
        "page_count": page_count,
        "total_native_chars": total_chars,
        "avg_chars_per_page": round(avg_chars, 1),
        "total_images": total_images,
        "avg_images_per_page": round(avg_images, 1),
    }

    is_image_based = (
        page_count >= min_pages
        and avg_chars < max_chars_per_page
        and avg_images >= min_images_per_page
    )
    return is_image_based, metrics


def extract(path: Path, options: ExtractOptions) -> ExtractedDocument:
    if fitz is None:
        raise MissingDependencyError(
            "Le package 'pymupdf' est requis pour extraire les fichiers .pdf. "
            "Installez l'extra : pip install 'trimtokens[pdf]'"
        )
    pdf = fitz.open(str(path))
    try:
        title = pdf.metadata.get("title") or None

        pages_native: list[str] = []
        pages_to_ocr: list[int] = []
        total_images = 0
        for i, page in enumerate(pdf):
            native = page.get_text("text") or ""
            pages_native.append(native)
            with contextlib.suppress(Exception):
                total_images += len(page.get_images(full=False))

            if options.no_ocr:
                continue
            if options.force_ocr or len(native.strip()) < options.pdf_min_native_chars_per_page:
                pages_to_ocr.append(i)

        ocr_results: dict[int, str] = {}
        if pages_to_ocr:
            ocr_results = _ocr_pages(pdf, pages_to_ocr, options)

        # Assemblage : OCR remplace le natif uniquement si OCR a produit du texte
        final_pages: list[str] = []
        used_ocr: list[int] = []
        for i, native in enumerate(pages_native):
            ocr_text = ocr_results.get(i, "").strip()
            if ocr_text and (options.force_ocr or len(native.strip()) < options.pdf_min_native_chars_per_page):
                final_pages.append(ocr_text)
                used_ocr.append(i)
            else:
                final_pages.append(native)
    finally:
        pdf.close()

    cleaned_pages = strip_recurring_headers_footers(final_pages)

    # Détection PDF image-based APRÈS strip headers : sinon les en-têtes répétés
    # gonflent artificiellement le compte de caractères natifs. On évalue donc le
    # contenu réellement extractible (hors boilerplate cross-pages).
    is_image_based, image_metrics = detect_image_based(
        cleaned_pages,
        total_images,
        max_chars_per_page=options.pdf_image_based_max_chars_per_page,
        min_images_per_page=options.pdf_image_based_min_images_per_page,
        min_pages=options.pdf_image_based_min_pages,
    )

    # Drop des pages quasi-vides (par défaut, indépendant du smart_filter).
    # Cible les pages blanches ou réduites à un numéro après OCR.
    empty_dropped: list[int] = []
    if options.drop_empty_pages:
        kept: list[str] = []
        page_mapping_after_empty: list[int] = []
        for i, text in enumerate(cleaned_pages):
            if len(text.split()) < options.empty_page_min_words:
                empty_dropped.append(i + 1)
            else:
                kept.append(text)
                page_mapping_after_empty.append(i)
        cleaned_pages = kept
    else:
        page_mapping_after_empty = list(range(len(cleaned_pages)))

    # Filtrage intelligent opt-in : TOC, bibliographie, pages éparses
    filtered_info: dict[str, list[int]] = {}
    page_mapping: list[int] = list(page_mapping_after_empty)  # idx final → idx original
    if options.smart_filter:
        analyses = analyze_pages(
            cleaned_pages,
            filter_toc=options.filter_toc,
            filter_bibliography=options.filter_bibliography,
            filter_sparse=options.filter_sparse,
        )
        kept_pages, raw_filtered = filter_pages(cleaned_pages, analyses)
        # Re-mapping : `raw_filtered` rapporte des indices post-empty-drop (1-based).
        # On les convertit en numéros de page ORIGINAUX (1-based) pour l'utilisateur.
        filtered_info = {
            cat: [page_mapping_after_empty[i - 1] + 1 for i in idxs]
            for cat, idxs in raw_filtered.items()
        }
        page_mapping = [
            page_mapping_after_empty[i] for i, a in enumerate(analyses) if not a.should_filter
        ]
        cleaned_pages = kept_pages

    # Marque pages "continuation" (paragraphe enchaîne) pour omettre header MD
    continuation_flags = (
        mark_continuations(cleaned_pages) if options.merge_continuations
        else [False] * len(cleaned_pages)
    )

    sections: list[Section] = []
    for new_idx, text in enumerate(cleaned_pages):
        original_idx = page_mapping[new_idx]
        is_ocr = original_idx in used_ocr
        header = f"Page {original_idx + 1}" + (" (OCR)" if is_ocr else "")
        section_meta: dict[str, object] = {}
        if continuation_flags[new_idx]:
            section_meta["continuation"] = True
        sections.append(Section(header=header, content=text, metadata=section_meta))

    metadata: dict[str, object] = {"language": options.ocr_languages if used_ocr else ""}
    if filtered_info and any(filtered_info.values()):
        metadata["filtered_pages"] = filtered_info
    if empty_dropped:
        metadata["empty_pages_dropped"] = empty_dropped

    # Avertissement PDF image-based si pas de texte extrait via OCR
    if is_image_based and not used_ocr:
        metadata["image_based"] = True
        metadata["image_based_metrics"] = image_metrics
        _emit_image_based_warning(path, image_metrics, options)
    elif is_image_based:
        metadata["image_based"] = True
        metadata["image_based_metrics"] = image_metrics

    return ExtractedDocument(
        source_path=path,
        source_type="pdf",
        title=title,
        sections=sections,
        ocr_used=bool(used_ocr),
        ocr_pages=[i + 1 for i in sorted(used_ocr)],
        metadata=metadata,
    )


def _emit_image_based_warning(
    path: Path, metrics: dict[str, float], options: ExtractOptions
) -> None:
    """Affiche un avertissement clair pour les PDF image-based sans OCR effectif."""
    from trimtokens.ocr.backend import get_backend

    backend = get_backend(options.ocr_backend)
    available = backend.is_available()

    if options.no_ocr:
        reason = "OCR désactivé (--no-ocr)"
    elif not available:
        reason = f"Backend OCR '{backend.name}' indisponible"
    else:
        reason = "OCR n'a pas produit de texte exploitable"

    msg_lines = [
        f"PDF '{path.name}' semble image-based mais aucun OCR n'a été appliqué.",
        f"  - {int(metrics['page_count'])} pages",
        f"  - {metrics['avg_chars_per_page']:.0f} caractères natifs / page (seuil < 100)",
        f"  - {metrics['avg_images_per_page']:.1f} images / page (seuil >= 2)",
        f"  Raison : {reason}",
    ]
    if not available and not options.no_ocr:
        msg_lines.append("")
        msg_lines.append(backend.install_hint())
        msg_lines.append("Puis relancer avec : --force-ocr")

    log.warning("\n".join(msg_lines))


def _ocr_pages(
    pdf: Any, page_indices: list[int], options: ExtractOptions
) -> dict[int, str]:
    """Rastérise les pages indiquées puis lance OCR (avec cache + parallel optionnel)."""
    from trimtokens.ocr.backend import get_backend

    backend = get_backend(options.ocr_backend)
    if not backend.is_available():
        log.warning(
            "Backend OCR '%s' indisponible — OCR ignoré pour %d page(s) du PDF '%s'.\n%s",
            backend.name,
            len(page_indices),
            pdf.name,
            backend.install_hint(),
        )
        log_event(
            log,
            Events.OCR_SKIPPED,
            backend=backend.name,
            pdf=pdf.name,
            pages=len(page_indices),
            reason="backend_unavailable",
        )
        return {}

    log_event(
        log,
        Events.OCR_START,
        backend=backend.name,
        pdf=pdf.name,
        pages=len(page_indices),
    )
    t_ocr_start = time.perf_counter()

    from trimtokens.ocr.cache import OCRCache, compute_cache_key

    cache = OCRCache() if options.use_cache else None

    # Rastérisation séquentielle (rapide, ne nécessite pas Tesseract)
    rastered: list[tuple[int, bytes]] = []
    for idx in page_indices:
        page = pdf[idx]
        pix = page.get_pixmap(dpi=options.pdf_ocr_dpi)
        rastered.append((idx, pix.tobytes("png")))

    # Cache lookup. Clé inclut le backend pour éviter de mélanger les résultats
    # entre moteurs (tesseract vs paddleocr produisent des textes différents).
    results: dict[int, str] = {}
    pending: list[tuple[int, bytes, int, str]] = []  # (idx, image_bytes, psm, cache_key)
    cache_lang_key = f"{backend.name}:{options.ocr_languages}"
    cache_hits = 0
    for idx, image_bytes in rastered:
        psm = _psm_for_page(idx, options)
        if cache is not None:
            key = compute_cache_key(image_bytes, cache_lang_key, psm)
            cached = cache.get(key)
            if cached is not None:
                results[idx] = cached
                cache_hits += 1
                continue
        else:
            key = ""
        pending.append((idx, image_bytes, psm, key))

    if cache is not None and cache_hits:
        log_event(log, Events.CACHE_HIT, backend=backend.name, hits=cache_hits)

    if not pending:
        log_event(
            log,
            Events.OCR_COMPLETE,
            backend=backend.name,
            pdf=pdf.name,
            pages=len(page_indices),
            cache_hits=cache_hits,
            duration_ms=round((time.perf_counter() - t_ocr_start) * 1000, 2),
        )
        return results

    # OCR multi-process si options.workers != 1 ET >1 page non cachée.
    # Sinon séquentiel (cf `_ocr_page_images` / `_resolve_ocr_workers`).
    workers_used = _resolve_ocr_workers(options.workers, len(pending))
    ocr_texts = _ocr_page_images(
        [(item[1], item[2]) for item in pending],
        options,
        backend,
    )

    for (idx, _image_bytes, _psm, key), text in zip(pending, ocr_texts, strict=True):
        results[idx] = text
        if cache is not None and key:
            cache.set(key, text)

    log_event(
        log,
        Events.OCR_COMPLETE,
        backend=backend.name,
        pdf=pdf.name,
        pages=len(page_indices),
        cache_hits=cache_hits,
        ocr_calls=len(pending),
        workers=workers_used,
        duration_ms=round((time.perf_counter() - t_ocr_start) * 1000, 2),
    )
    return results


def _psm_for_page(page_index: int, options: ExtractOptions) -> int:
    """Sélectionne le PSM Tesseract adapté au type de page.

    - Page 0 (couverture, généralement texte épars + titre central) : PSM 11
      (sparse text, no specific order). Améliore détection des titres dispersés.
    - Autres pages : `options.ocr_psm` (par défaut 6 = uniform block).
    """
    if page_index == 0:
        return 11
    return options.ocr_psm


def _ocr_worker(args: tuple[bytes, int, str, str]) -> str:
    """Worker top-level (picklable) pour `ProcessPoolExecutor`.

    Re-résout le backend dans le process enfant via le registry — chaque worker
    réinitialise lazy ses imports OCR (Tesseract, opencv, PIL). Conserve la
    sémantique de `OCREngine.extract` sans transporter d'instance via pickle.
    """
    image_bytes, psm, backend_name, languages = args

    from PIL import Image

    from trimtokens.ocr.backend import get_backend
    from trimtokens.ocr.preprocess import preprocess

    backend = get_backend(backend_name)
    with Image.open(io.BytesIO(image_bytes)) as img:
        processed = preprocess(img)
        return backend.extract(processed, languages=languages, psm=psm)


def _resolve_ocr_workers(requested: int, num_items: int) -> int:
    """Calcule le nombre effectif de workers OCR à utiliser.

    - `requested == 0` → auto : `default_workers()` borné par `num_items`.
    - `requested >= 1` → exact, borné par `num_items`.
    - `num_items <= 1` → toujours 1 (spawn overhead > gain).
    """
    from trimtokens.ocr.parallel import default_workers

    if num_items <= 1:
        return 1
    if requested <= 0:
        return min(default_workers(), num_items)
    return min(requested, num_items)


def _ocr_page_images(
    image_specs: list[tuple[bytes, int]],
    options: ExtractOptions,
    backend: OCREngine,
) -> list[str]:
    """OCR sur une liste (image_bytes, psm). PSM adapté par page. Backend injecté.

    Route vers `ocr.parallel.parallel_map` quand workers > 1 ET nb pages > 1.
    Sinon exécution séquentielle dans le process courant (évite spawn overhead).
    """
    if not image_specs:
        return []

    workers = _resolve_ocr_workers(options.workers, len(image_specs))

    if workers == 1:
        # Mode séquentiel : pas de pickling, pas de spawn. Identique au comportement
        # historique avant câblage multiprocessing.
        from PIL import Image

        from trimtokens.ocr.preprocess import preprocess

        texts: list[str] = []
        for image_bytes, psm in image_specs:
            with Image.open(io.BytesIO(image_bytes)) as img:
                processed = preprocess(img)
                text = backend.extract(
                    processed,
                    languages=options.ocr_languages,
                    psm=psm,
                )
            texts.append(text)
        return texts

    # Mode parallèle : dispatch via ProcessPoolExecutor. Args picklable
    # (bytes + int + str + str), backend ré-instancié dans chaque worker.
    from trimtokens.ocr.parallel import parallel_map

    worker_args: list[tuple[bytes, int, str, str]] = [
        (image_bytes, psm, backend.name, options.ocr_languages)
        for image_bytes, psm in image_specs
    ]
    return parallel_map(
        _ocr_worker,
        worker_args,
        workers=workers,
        show_progress=False,
        description=f"OCR ({backend.name})",
    )
