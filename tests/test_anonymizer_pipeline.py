"""Tests d'intégration : anonymisation câblée dans `core.process` et le renderer."""

from __future__ import annotations

from pathlib import Path

from trimtokens.anonymizer.mapping import AnonymizationMap
from trimtokens.core import process
from trimtokens.models import ExtractOptions

IBAN = "FR1420041010050500013M02606"
SAMPLE = f"Le client jean.dupont@example.fr règle sur {IBAN}, SIRET 40483304000011."


def _write(tmp_path: Path, text: str) -> Path:
    f = tmp_path / "contrat.txt"
    f.write_text(text, encoding="utf-8")
    return f


def test_process_without_anonymize_keeps_pii(tmp_path: Path) -> None:
    result = process(_write(tmp_path, SAMPLE), ExtractOptions())
    assert "jean.dupont@example.fr" in result.markdown
    assert not result.anonymized


def test_process_anonymize_removes_pii(tmp_path: Path) -> None:
    opts = ExtractOptions(anonymize=True, anon_ner=False)
    result = process(_write(tmp_path, SAMPLE), opts)
    assert result.anonymized
    assert "jean.dupont@example.fr" not in result.markdown
    assert IBAN not in result.markdown
    assert "[EMAIL_1]" in result.markdown
    assert result.anon_counts.get("EMAIL") == 1
    assert result.anon_counts.get("IBAN") == 1
    assert result.anon_counts.get("SIRET") == 1


def test_process_anonymize_frontmatter(tmp_path: Path) -> None:
    opts = ExtractOptions(anonymize=True, anon_ner=False)
    result = process(_write(tmp_path, SAMPLE), opts)
    assert "anonymized: true" in result.markdown
    assert "anonymized_entities:" in result.markdown


def test_process_anonymize_is_reversible(tmp_path: Path) -> None:
    opts = ExtractOptions(anonymize=True, anon_ner=False)
    result = process(_write(tmp_path, SAMPLE), opts)
    assert isinstance(result.anon_map, AnonymizationMap)
    restored = result.anon_map.deanonymize(result.markdown)
    assert "jean.dupont@example.fr" in restored
    assert IBAN in restored


def test_shared_strategy_consistent_across_files(tmp_path: Path) -> None:
    from trimtokens.anonymizer import PseudonymizeStrategy

    shared = PseudonymizeStrategy()
    f1 = tmp_path / "a.txt"
    f1.write_text("Contact jean.dupont@example.fr ici.", encoding="utf-8")
    f2 = tmp_path / "b.txt"
    f2.write_text("Encore jean.dupont@example.fr là.", encoding="utf-8")
    opts = ExtractOptions(anonymize=True, anon_ner=False)
    r1 = process(f1, opts, anon_strategy=shared)
    r2 = process(f2, opts, anon_strategy=shared)
    # Même email → même pseudonyme dans les deux documents.
    assert "[EMAIL_1]" in r1.markdown
    assert "[EMAIL_1]" in r2.markdown
    assert len(shared.mapping) == 1
