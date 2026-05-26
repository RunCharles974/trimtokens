"""Tests du renderer Markdown (front-matter YAML + sections)."""

from __future__ import annotations

from pathlib import Path

import yaml

from trimtokens.models import CleanStats, ExtractedDocument, Section
from trimtokens.renderer import build_frontmatter, render


def _make_doc(**overrides: object) -> ExtractedDocument:
    base = {
        "source_path": Path("example.pdf"),
        "source_type": "pdf",
        "title": "Titre du doc",
        "sections": [
            Section(header="Page 1", content="Contenu de la page 1."),
            Section(header="Page 2", content="Contenu de la page 2."),
        ],
        "metadata": {"language": "fra+eng"},
        "ocr_used": True,
        "ocr_pages": [2],
    }
    base.update(overrides)  # type: ignore[arg-type]
    return ExtractedDocument(**base)  # type: ignore[arg-type]


def _make_stats() -> CleanStats:
    return CleanStats(
        original_size_bytes=2_500_000,
        cleaned_size_bytes=20_000,
        original_chars=300_000,
        cleaned_chars=40_000,
        tokens_estimated=10_000,
        tokens_original_estimated=75_000,
    )


def test_render_produces_yaml_frontmatter_block() -> None:
    output = render(_make_doc(), _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    assert output.startswith("---\n")
    assert "\n---\n" in output[4:]


def test_frontmatter_contains_required_keys() -> None:
    fm = build_frontmatter(_make_doc(), _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    data = yaml.safe_load(fm)
    assert data["source"] == "example.pdf"
    assert data["type"] == "pdf"
    assert data["extracted_at"] == "2026-05-25T12:00:00Z"
    assert data["ocr_used"] is True
    assert data["ocr_pages"] == [2]
    assert data["language"] == "fra+eng"
    stats = data["stats"]
    assert stats["original_size_bytes"] == 2_500_000
    assert stats["cleaned_size_bytes"] == 20_000
    assert stats["original_chars"] == 300_000
    assert stats["cleaned_chars"] == 40_000
    assert stats["tokens_estimated"] == 10_000
    assert stats["tokens_original_estimated"] == 75_000
    assert "reduction_percent" in stats
    assert "tokens_reduction_percent" in stats


def test_render_includes_title_and_sections() -> None:
    output = render(_make_doc(), _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    assert "# Titre du doc" in output
    assert "## Page 1" in output
    assert "Contenu de la page 1." in output
    assert "## Page 2" in output
    assert "Contenu de la page 2." in output


def test_render_handles_document_without_title() -> None:
    doc = _make_doc(title=None)
    output = render(doc, _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    assert "\n# " not in output.split("---\n---\n")[-1]


def test_render_handles_empty_sections() -> None:
    doc = _make_doc(sections=[])
    output = render(doc, _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    assert output.endswith("\n")
    assert "## " not in output


def test_render_handles_section_without_header() -> None:
    doc = _make_doc(sections=[Section(header="", content="Contenu brut.")])
    output = render(doc, _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    assert "Contenu brut." in output
    assert "## " not in output


def test_frontmatter_unicode_safe() -> None:
    doc = _make_doc(title="Café — édition spéciale", metadata={"language": "fra"})
    fm = build_frontmatter(doc, _make_stats(), extracted_at="2026-05-25T12:00:00Z")
    # yaml allow_unicode doit conserver caractères accentués sans encodage \u
    data = yaml.safe_load(fm)
    assert data["language"] == "fra"
