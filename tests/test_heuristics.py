"""Tests des heuristiques de filtrage intelligent (TOC, biblio, pages éparses)."""

from __future__ import annotations

from trimtokens.cleaners.heuristics import (
    analyze_pages,
    detect_bibliography,
    detect_sparse,
    detect_toc,
    filter_pages,
)

# --- TOC ---------------------------------------------------------------------


def test_detect_toc_via_title() -> None:
    text = "Table des matières\n\nIntroduction\nMéthode\nRésultats"
    is_toc, reason = detect_toc(text)
    assert is_toc
    assert "TOC" in reason or "titre" in reason.lower()


def test_detect_toc_via_dotted_lines() -> None:
    text = (
        "Introduction ........... 1\n"
        "Chapitre 1 ............ 5\n"
        "Chapitre 2 ........... 15\n"
        "Chapitre 3 ........... 28\n"
        "Conclusion ........... 42\n"
        "Bibliographie ........ 50\n"
    )
    is_toc, reason = detect_toc(text)
    assert is_toc
    assert "lignes" in reason or "TOC" in reason


def test_detect_toc_via_spaced_lines() -> None:
    text = (
        "Introduction                1\n"
        "Chapitre 1                  5\n"
        "Chapitre 2                 15\n"
        "Chapitre 3                 28\n"
        "Conclusion                 42\n"
        "Bibliographie              50\n"
    )
    is_toc, _ = detect_toc(text)
    assert is_toc


def test_detect_toc_negative_normal_text() -> None:
    text = (
        "Ceci est un paragraphe ordinaire d'un document. "
        "Il contient du texte continu sans listes numerotées "
        "et sans renvois à des numéros de page."
    )
    is_toc, _ = detect_toc(text)
    assert not is_toc


def test_detect_toc_english_title() -> None:
    text = "Table of Contents\n\nIntroduction\nMethods"
    is_toc, _ = detect_toc(text)
    assert is_toc


# --- Bibliographie -----------------------------------------------------------


def test_detect_bibliography_via_title() -> None:
    text = "Bibliographie\n\n[1] Dupont, J. (2020). Etude X. Editeur."
    is_biblio, reason = detect_bibliography(text)
    assert is_biblio
    assert "titre" in reason.lower() or "Bibliographie" in reason


def test_detect_bibliography_via_bracket_refs() -> None:
    text = " ".join(f"[{i}] Auteur{i}, 20{20+i}. Titre. Editeur." for i in range(1, 12))
    is_biblio, _ = detect_bibliography(text)
    assert is_biblio


def test_detect_bibliography_via_author_year() -> None:
    refs = " ".join(
        f"voir (Dupont, {2010 + i}) pour plus de détails."
        for i in range(10)
    )
    is_biblio, _ = detect_bibliography(refs)
    assert is_biblio


def test_detect_bibliography_negative_short_text() -> None:
    text = "Ce paragraphe cite (Dupont, 2020) une seule fois."
    is_biblio, _ = detect_bibliography(text)
    assert not is_biblio


def test_detect_bibliography_english_title() -> None:
    text = "References\n\n[1] Smith J. (2021)"
    is_biblio, _ = detect_bibliography(text)
    assert is_biblio


# --- Pages éparses -----------------------------------------------------------


def test_detect_sparse_low_word_count() -> None:
    text = "Quelques mots seulement."
    is_sparse, _ = detect_sparse(text, word_count=len(text.split()))
    assert is_sparse


def test_detect_sparse_negative_dense_text() -> None:
    text = " ".join(["mot"] * 100)
    is_sparse, _ = detect_sparse(text, word_count=100)
    assert not is_sparse


# --- analyze_pages -----------------------------------------------------------


def test_analyze_pages_classifies_mixed_doc() -> None:
    pages = [
        # Page 1 : couverture (sparse)
        "TITRE\nAuteur",
        # Page 2 : TOC
        (
            "Sommaire\n\n"
            "Introduction ........... 3\n"
            "Méthode ................ 5\n"
            "Résultats ............. 12\n"
            "Discussion ............ 25\n"
            "Conclusion ............ 35\n"
            "Bibliographie ......... 40\n"
        ),
        # Page 3 : contenu normal
        " ".join(["mot"] * 200),
        # Page 4 : bibliographie
        "Bibliographie\n\n" + " ".join(f"[{i}] Auteur{i}, 20{i:02}." for i in range(1, 12)),
    ]
    analyses = analyze_pages(pages)

    assert analyses[0].is_sparse, "page 1 doit être sparse"
    assert analyses[1].is_toc, "page 2 doit être TOC"
    assert not analyses[2].should_filter, "page 3 doit être conservée"
    assert analyses[3].is_bibliography, "page 4 doit être bibliographie"


def test_analyze_pages_respects_disabled_flags() -> None:
    pages = ["Sommaire\nIntro 1\nMéthode 5\nFin 10", "x" * 5]
    analyses = analyze_pages(pages, filter_toc=False, filter_sparse=False)
    assert not analyses[0].is_toc
    assert not analyses[1].is_sparse


def test_filter_pages_returns_kept_and_filtered_map() -> None:
    pages = [
        "Sommaire\n\nIntro ........ 1\nMéthode ...... 5\nRésultat ..... 10\n"
        "Discussion .... 15\nConclusion ... 20\nBiblio ........ 25",  # TOC
        " ".join(["contenu"] * 200),  # normal
        "Court.",  # sparse
        " ".join(["normal"] * 100),  # normal
    ]
    analyses = analyze_pages(pages)
    kept, filtered = filter_pages(pages, analyses)

    assert len(kept) == 2  # pages 2 et 4 gardées
    assert 1 in filtered["toc"]
    assert 3 in filtered["sparse"]


# --- Intégration extracteur PDF ----------------------------------------------


def test_pdf_smart_filter_removes_toc_pages(tmp_path) -> None:
    import pytest

    fitz = pytest.importorskip("fitz")

    from trimtokens.extractors.pdf import extract
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "with_toc.pdf"
    doc = fitz.open()

    # Page 1 : TOC explicite
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Sommaire\n\n"
        "Introduction ........... 1\n"
        "Chapitre 1 ............ 5\n"
        "Chapitre 2 ........... 15\n"
        "Chapitre 3 ........... 28\n"
        "Conclusion ........... 42\n"
        "Bibliographie ........ 50",
    )

    # Pages 2-4 : contenu normal (texte wrappé via \n pour ne pas déborder)
    for i in range(3):
        page = doc.new_page()
        body = "\n".join(
            f"Ligne {j} du contenu principal de la page {i + 2} avec assez de mots."
            for j in range(15)
        )
        page.insert_text((72, 72), body)

    doc.save(str(pdf_path))
    doc.close()

    # Sans smart_filter : 4 sections
    result_normal = extract(pdf_path, ExtractOptions(no_ocr=True))
    assert len(result_normal.sections) == 4

    # Avec smart_filter : 3 sections (TOC retirée)
    result_filtered = extract(pdf_path, ExtractOptions(no_ocr=True, smart_filter=True))
    assert len(result_filtered.sections) == 3
    assert "filtered_pages" in result_filtered.metadata
    filtered_pages = result_filtered.metadata["filtered_pages"]
    assert isinstance(filtered_pages, dict)
    assert 1 in filtered_pages["toc"]


def test_detect_image_based_positive() -> None:
    """PDF avec peu de chars natifs et beaucoup d'images → image-based."""
    from trimtokens.extractors.pdf import detect_image_based

    # 10 pages, ~20 chars/page (headers seulement), 5 images/page
    pages = ["Page N / Header" for _ in range(10)]
    is_img, metrics = detect_image_based(pages, total_images=50)
    assert is_img
    assert metrics["avg_chars_per_page"] < 100
    assert metrics["avg_images_per_page"] >= 2


def test_detect_image_based_negative_text_pdf() -> None:
    """PDF avec beaucoup de texte natif → pas image-based."""
    from trimtokens.extractors.pdf import detect_image_based

    pages = ["Contenu textuel substantiel sur cette page. " * 50 for _ in range(10)]
    is_img, _ = detect_image_based(pages, total_images=2)
    assert not is_img


def test_detect_image_based_negative_too_few_pages() -> None:
    """Doc < 3 pages : pas assez d'échantillon, pas de classification."""
    from trimtokens.extractors.pdf import detect_image_based

    pages = ["x", "y"]
    is_img, _ = detect_image_based(pages, total_images=10)
    assert not is_img


def test_detect_image_based_empty_doc() -> None:
    from trimtokens.extractors.pdf import detect_image_based

    is_img, metrics = detect_image_based([], total_images=0)
    assert not is_img
    assert metrics["page_count"] == 0


def test_pdf_smart_filter_can_disable_specific_detector(tmp_path) -> None:
    import pytest

    fitz = pytest.importorskip("fitz")

    from trimtokens.extractors.pdf import extract
    from trimtokens.models import ExtractOptions

    pdf_path = tmp_path / "with_biblio.pdf"
    doc = fitz.open()

    # Page 1 : contenu normal (wrappé)
    page = doc.new_page()
    body = "\n".join(
        f"Ligne {j} du contenu principal de la page 1 avec suffisamment de mots ici."
        for j in range(15)
    )
    page.insert_text((72, 72), body)

    # Page 2 : bibliographie
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Bibliographie\n\n" + "\n".join(f"[{i}] Auteur, 20{i:02}. Titre." for i in range(1, 12)),
    )

    doc.save(str(pdf_path))
    doc.close()

    # smart_filter actif mais filter_bibliography=False : garde la biblio
    result = extract(
        pdf_path,
        ExtractOptions(no_ocr=True, smart_filter=True, filter_bibliography=False),
    )
    assert len(result.sections) == 2  # Biblio conservée
