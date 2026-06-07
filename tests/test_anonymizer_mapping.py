"""Tests de la table de correspondance (`anonymizer.mapping`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trimtokens.anonymizer.mapping import (
    AnonymizationMap,
    MappingError,
    merge_maps,
)
from trimtokens.anonymizer.recognizers import EntityType


def test_pseudonym_is_idempotent() -> None:
    m = AnonymizationMap()
    a = m.pseudonym(EntityType.EMAIL, "a@b.fr")
    b = m.pseudonym(EntityType.EMAIL, "a@b.fr")
    assert a == b == "[EMAIL_1]"
    assert len(m) == 1


def test_counters_per_type() -> None:
    m = AnonymizationMap()
    assert m.pseudonym(EntityType.EMAIL, "a@b.fr") == "[EMAIL_1]"
    assert m.pseudonym(EntityType.EMAIL, "c@d.fr") == "[EMAIL_2]"
    assert m.pseudonym(EntityType.IBAN, "FR14...") == "[IBAN_1]"


def test_deanonymize_restores_values() -> None:
    m = AnonymizationMap()
    t1 = m.pseudonym(EntityType.EMAIL, "a@b.fr")
    t2 = m.pseudonym(EntityType.IBAN, "FR1420041010050500013M02606")
    text = f"Mail {t1}, banque {t2}, encore {t1}."
    restored = m.deanonymize(text)
    assert restored == "Mail a@b.fr, banque FR1420041010050500013M02606, encore a@b.fr."


def test_deanonymize_no_prefix_collision() -> None:
    m = AnonymizationMap()
    tags = [m.pseudonym(EntityType.EMAIL, f"user{i}@x.fr") for i in range(12)]
    text = " ".join(tags)
    restored = m.deanonymize(text)
    assert "user11@x.fr" in restored
    assert "[EMAIL_" not in restored


def test_dict_roundtrip() -> None:
    m = AnonymizationMap()
    m.pseudonym(EntityType.EMAIL, "a@b.fr")
    m.pseudonym(EntityType.SIRET, "40483304000011")
    clone = AnonymizationMap.from_dict(m.to_dict())
    assert [e.value for e in clone.entries()] == ["a@b.fr", "40483304000011"]
    # Compteur reconstruit : le prochain tag continue la numérotation.
    assert clone.pseudonym(EntityType.EMAIL, "c@d.fr") == "[EMAIL_2]"


def test_from_dict_rejects_malformed() -> None:
    with pytest.raises(MappingError):
        AnonymizationMap.from_dict({"version": 1})
    with pytest.raises(MappingError):
        AnonymizationMap.from_dict({"entries": [{"tag": "x", "type": "INCONNU", "value": "v"}]})


def test_json_file_roundtrip(tmp_path: Path) -> None:
    m = AnonymizationMap()
    m.pseudonym(EntityType.EMAIL, "a@b.fr")
    path = tmp_path / "map.json"
    m.save_json(path)
    loaded = AnonymizationMap.load_json(path)
    assert loaded.deanonymize("[EMAIL_1]") == "a@b.fr"


def test_load_json_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(MappingError):
        AnonymizationMap.load_json(bad)


def test_merge_maps_keeps_value_consistency() -> None:
    m1 = AnonymizationMap()
    m1.pseudonym(EntityType.EMAIL, "shared@x.fr")
    m2 = AnonymizationMap()
    m2.pseudonym(EntityType.EMAIL, "shared@x.fr")
    m2.pseudonym(EntityType.EMAIL, "other@x.fr")
    merged = merge_maps([m1, m2])
    assert len(merged) == 2  # shared dédupliqué


# --- Chiffrement (extra [anonymize]) ----------------------------------------


def test_encrypted_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    m = AnonymizationMap()
    m.pseudonym(EntityType.IBAN, "FR1420041010050500013M02606")
    path = tmp_path / "map.enc"
    m.save_encrypted(path, "passphrase-secrète")
    loaded = AnonymizationMap.load_encrypted(path, "passphrase-secrète")
    assert loaded.deanonymize("[IBAN_1]") == "FR1420041010050500013M02606"
    # Le fichier ne contient pas la valeur en clair.
    assert b"FR1420041010050500013M02606" not in path.read_bytes()


def test_encrypted_wrong_passphrase(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    m = AnonymizationMap()
    m.pseudonym(EntityType.EMAIL, "a@b.fr")
    path = tmp_path / "map.enc"
    m.save_encrypted(path, "bonne")
    with pytest.raises(MappingError):
        AnonymizationMap.load_encrypted(path, "mauvaise")
