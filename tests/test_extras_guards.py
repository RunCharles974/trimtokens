"""Tests des garde-fous ImportError dans les extracteurs (extras packaging).

Vérifie que `MissingDependencyError` est levé proprement quand une dep
optionnelle est absente, avec un message orientant vers l'extra à installer.
On mock le module-level binding `Document`/`Presentation`/etc. à `None` pour
simuler l'absence sans désinstaller la dep.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trimtokens.exceptions import MissingDependencyError
from trimtokens.models import ExtractOptions


def test_docx_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import docx as docx_module

    monkeypatch.setattr(docx_module, "Document", None)

    f = tmp_path / "x.docx"
    f.write_bytes(b"fake")

    with pytest.raises(MissingDependencyError, match=r"python-docx.*\[office\]"):
        docx_module.extract(f, ExtractOptions())


def test_pptx_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import pptx as pptx_module

    monkeypatch.setattr(pptx_module, "Presentation", None)

    f = tmp_path / "x.pptx"
    f.write_bytes(b"fake")

    with pytest.raises(MissingDependencyError, match=r"python-pptx.*\[office\]"):
        pptx_module.extract(f, ExtractOptions())


def test_xlsx_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import xlsx_csv

    monkeypatch.setattr(xlsx_csv, "load_workbook", None)

    f = tmp_path / "x.xlsx"
    f.write_bytes(b"fake")

    with pytest.raises(MissingDependencyError, match=r"openpyxl.*\[office\]"):
        xlsx_csv.extract(f, ExtractOptions())


def test_xlsx_csv_extractor_still_works_for_csv_without_openpyxl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSV utilise stdlib `csv`, openpyxl absent ne doit pas bloquer."""
    from trimtokens.extractors import xlsx_csv

    monkeypatch.setattr(xlsx_csv, "load_workbook", None)

    f = tmp_path / "data.csv"
    f.write_text("col1,col2\na,1\nb,2\n", encoding="utf-8")

    doc = xlsx_csv.extract(f, ExtractOptions())
    assert doc.source_type == "csv"
    assert doc.sections  # contenu extrait


def test_html_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import html as html_module

    monkeypatch.setattr(html_module, "BeautifulSoup", None)

    f = tmp_path / "x.html"
    f.write_text("<html><body>hi</body></html>", encoding="utf-8")

    with pytest.raises(MissingDependencyError, match=r"beautifulsoup4.*\[web\]"):
        html_module.extract(f, ExtractOptions())


def test_pdf_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import pdf as pdf_module

    monkeypatch.setattr(pdf_module, "fitz", None)

    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-fake")

    with pytest.raises(MissingDependencyError, match=r"pymupdf.*\[pdf\]"):
        pdf_module.extract(f, ExtractOptions())


def test_rtf_missing_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trimtokens.extractors import rtf as rtf_module

    monkeypatch.setattr(rtf_module, "rtf_to_text", None)

    f = tmp_path / "x.rtf"
    f.write_text("{\\rtf1 hi}", encoding="utf-8")

    with pytest.raises(MissingDependencyError, match=r"striprtf"):
        rtf_module.extract(f, ExtractOptions())


def test_missing_dep_error_inherits_trimtokens_error() -> None:
    """`MissingDependencyError` doit être attrapable comme `TrimTokensError`."""
    from trimtokens.exceptions import TrimTokensError

    assert issubclass(MissingDependencyError, TrimTokensError)


def test_core_process_propagates_missing_dep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """core.process route vers l'extracteur, qui lève MissingDependencyError."""
    from trimtokens.core import process
    from trimtokens.extractors import pdf as pdf_module

    monkeypatch.setattr(pdf_module, "fitz", None)

    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-fake")

    with pytest.raises(MissingDependencyError):
        process(f)
