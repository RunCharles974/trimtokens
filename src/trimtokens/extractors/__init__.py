"""Extracteurs par format.

Un module par format, signature unique :

    def extract(path: Path, options: ExtractOptions) -> ExtractedDocument: ...
"""

from __future__ import annotations

EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx_csv",
    ".csv": "xlsx_csv",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt_md",
    ".md": "txt_md",
    ".markdown": "txt_md",
    ".rtf": "rtf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".bmp": "image",
    ".heic": "image",
    ".heif": "image",
}

__all__ = ["EXTENSION_MAP"]
