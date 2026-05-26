"""Renderer Markdown : transforme un `ExtractedDocument` en chaîne Markdown.

Front-matter YAML obligatoire (cf TrimTokens.md §5) avec stats complètes,
puis titre du document, puis sections (chacune avec son header `##`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml

from trimtokens.models import CleanStats, ExtractedDocument


def _now_iso() -> str:
    """Timestamp ISO 8601 UTC sans microsecondes."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_frontmatter(
    document: ExtractedDocument,
    stats: CleanStats,
    *,
    extracted_at: str | None = None,
) -> str:
    """Construit le bloc YAML de front-matter."""
    data: dict[str, Any] = {
        "source": document.source_path.name,
        "type": document.source_type,
        "extracted_at": extracted_at or _now_iso(),
        "ocr_used": document.ocr_used,
        "ocr_pages": document.ocr_pages,
        "language": document.metadata.get("language", ""),
        "stats": {
            "original_size_bytes": stats.original_size_bytes,
            "cleaned_size_bytes": stats.cleaned_size_bytes,
            "reduction_percent": stats.reduction_percent,
            "original_chars": stats.original_chars,
            "cleaned_chars": stats.cleaned_chars,
            "tokens_estimated": stats.tokens_estimated,
            "tokens_original_estimated": stats.tokens_original_estimated,
            "tokens_reduction_percent": stats.tokens_reduction_percent,
            "tokens_input_estimated": stats.tokens_input_estimated,
            "tokens_input_reduction_percent": stats.tokens_input_reduction_percent,
        },
    }
    # Pages filtrées par les heuristiques intelligentes (si applicable)
    filtered = document.metadata.get("filtered_pages")
    if filtered:
        data["filtered_pages"] = filtered
    # Flag PDF image-based (avertit l'utilisateur que le contenu nécessite OCR)
    if document.metadata.get("image_based"):
        data["image_based"] = True
        metrics = document.metadata.get("image_based_metrics")
        if metrics:
            data["image_based_metrics"] = metrics
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def render(
    document: ExtractedDocument,
    stats: CleanStats,
    *,
    extracted_at: str | None = None,
) -> str:
    """Rend un `ExtractedDocument` en Markdown avec front-matter YAML."""
    frontmatter = build_frontmatter(document, stats, extracted_at=extracted_at)

    parts: list[str] = ["---", frontmatter.rstrip(), "---", ""]

    if document.title:
        parts.append(f"# {document.title}")
        parts.append("")

    for section in document.sections:
        # Section marquée "continuation" (texte enchaîne avec section précédente) :
        # on omet le header `## Page N` pour préserver le flot du paragraphe.
        is_continuation = bool(section.metadata.get("continuation"))
        if section.header and not is_continuation:
            parts.append(f"## {section.header}")
            parts.append("")
        content = section.content.rstrip()
        if content:
            parts.append(content)
            parts.append("")

    while parts and parts[-1] == "":
        parts.pop()
    parts.append("")

    return "\n".join(parts)
