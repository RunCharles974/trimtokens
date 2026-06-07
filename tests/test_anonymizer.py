"""Tests de la détection PII par regex validées (`anonymizer.recognizers`).

Les valeurs d'exemple sont *synthétiques mais arithmétiquement valides* (Luhn,
modulo 97, clé NIR) afin de vérifier le couple regex + validateur. Elles ne
correspondent à aucune personne réelle.
"""

from __future__ import annotations

from trimtokens.anonymizer import EntityType, find_pii
from trimtokens.anonymizer.recognizers import (
    _credit_card_ok,
    _iban_ok,
    _luhn_ok,
    _nir_ok,
    _vat_fr_ok,
)

# Échantillons valides (calculés).
VALID_SIREN = "404833048"
VALID_SIRET = "40483304000011"
VALID_VAT = "FR83404833048"
VALID_NIR = "185127505300124"
VALID_IBAN = "FR1420041010050500013M02606"
VALID_CB = "4532015112830366"


def _types(text: str) -> list[EntityType]:
    return [m.entity_type for m in find_pii(text)]


# --- Validateurs arithmétiques ----------------------------------------------


def test_luhn_accepts_valid() -> None:
    assert _luhn_ok(VALID_SIREN)
    assert _luhn_ok(VALID_SIRET)


def test_luhn_rejects_invalid() -> None:
    assert not _luhn_ok("404833047")
    assert not _luhn_ok("123456789")


def test_iban_checksum() -> None:
    assert _iban_ok(VALID_IBAN)
    assert _iban_ok("FR14 2004 1010 0505 0001 3M02 606")  # espaces tolérés
    assert not _iban_ok("FR0020041010050500013M02606")


def test_nir_key() -> None:
    assert _nir_ok(VALID_NIR)
    assert not _nir_ok("185127505300199")  # clé fausse


def test_nir_corse() -> None:
    # Département 2A : la clé doit être calculée après substitution 2A→19.
    body = "185122A05300"
    body13 = body + "1"
    numeric = int(body13.replace("2A", "19"))
    key = 97 - (numeric % 97)
    assert _nir_ok(f"{body13}{key:02d}")


def test_vat_fr() -> None:
    assert _vat_fr_ok(VALID_VAT)
    assert not _vat_fr_ok("FR00404833048")


def test_credit_card_luhn() -> None:
    assert _credit_card_ok(VALID_CB)
    assert _credit_card_ok("4532 0151 1283 0366")
    assert not _credit_card_ok("4532015112830367")


# --- Détection bout en bout -------------------------------------------------


def test_detect_email() -> None:
    matches = find_pii("Contact : jean.dupont@example.fr pour suite.")
    assert len(matches) == 1
    assert matches[0].entity_type is EntityType.EMAIL
    assert matches[0].value == "jean.dupont@example.fr"


def test_detect_phone_formats() -> None:
    assert _types("Tel 06 12 34 56 78") == [EntityType.PHONE]
    assert _types("Appeler +33 6 12 34 56 78") == [EntityType.PHONE]
    assert _types("ligne 0612345678 sur") == [EntityType.PHONE]


def test_detect_iban() -> None:
    assert EntityType.IBAN in _types(f"Virement {VALID_IBAN} merci")


def test_detect_nir() -> None:
    assert EntityType.NIR in _types(f"NIR {VALID_NIR} du salarié")


def test_detect_vat() -> None:
    assert EntityType.VAT in _types(f"TVA {VALID_VAT}.")


def test_detect_license_plate() -> None:
    assert _types("Véhicule AB-123-CD garé") == [EntityType.LICENSE_PLATE]


def test_offsets_are_exact() -> None:
    text = f"Société immatriculée {VALID_SIRET} active."
    matches = find_pii(text)
    assert matches
    for m in matches:
        assert text[m.start : m.end] == m.value


# --- Précision : pas de faux positifs ---------------------------------------


def test_invalid_siren_not_detected() -> None:
    # 9 chiffres mais Luhn faux → aucune détection SIREN/SIRET.
    assert EntityType.SIREN not in _types("Référence 123456789 interne")


def test_invalid_iban_not_detected() -> None:
    assert EntityType.IBAN not in _types("Code FR0020041010050500013M02606 erroné")


def test_plain_text_yields_nothing() -> None:
    assert find_pii("Le présent contrat prend effet ce jour.") == []


# --- Chevauchements ---------------------------------------------------------


def test_siret_not_double_counted_as_siren() -> None:
    types = _types(f"SIRET {VALID_SIRET} fin")
    assert EntityType.SIRET in types
    assert EntityType.SIREN not in types


def test_vat_swallows_inner_siren() -> None:
    types = _types(f"Numéro {VALID_VAT} ici")
    assert EntityType.VAT in types
    assert EntityType.SIREN not in types


def test_matches_returned_in_document_order() -> None:
    text = f"Mail a@b.fr puis tel 06 12 34 56 78 enfin {VALID_IBAN}"
    starts = [m.start for m in find_pii(text)]
    assert starts == sorted(starts)
