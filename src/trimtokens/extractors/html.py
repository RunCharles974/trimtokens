"""Extracteur HTML : nettoyage via beautifulsoup4 puis conversion Markdown via markdownify.

Étapes :
- Détection encodage et décodage du fichier
- Suppression `<script>`, `<style>`, `<noscript>`, `<iframe>`, balises non textuelles
- Extraction du `<title>` pour le titre du document
- Conversion du `<body>` (ou de la racine) en Markdown avec `heading_style="ATX"`
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

from trimtokens.extractors._encoding import detect_encoding
from trimtokens.models import ExtractedDocument, ExtractOptions, Section

_STRIP_TAGS = ("script", "style", "noscript", "iframe", "template", "head")


def extract(path: Path, options: ExtractOptions) -> ExtractedDocument:
    raw = path.read_bytes()
    encoding = detect_encoding(raw)
    html_text = raw.decode(encoding, errors="replace")

    soup = BeautifulSoup(html_text, "html.parser")

    title_tag = soup.find("title")
    title: str | None = title_tag.get_text(strip=True) if title_tag else None

    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    body = soup.find("body") or soup
    markdown_content = html_to_markdown(str(body), heading_style="ATX")

    return ExtractedDocument(
        source_path=path,
        source_type="html",
        title=title,
        sections=[Section(header="", content=markdown_content)],
        metadata={"encoding": encoding},
    )
