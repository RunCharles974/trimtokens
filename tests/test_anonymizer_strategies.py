"""Tests des stratégies de substitution et du round-trip d'anonymisation."""

from __future__ import annotations

from trimtokens.anonymizer import (
    AnonymizationResult,
    EntityType,
    HashStrategy,
    PartialMaskStrategy,
    PseudonymizeStrategy,
    RedactStrategy,
    anonymize_text,
)
from trimtokens.anonymizer.recognizers import RecognizerMatch
from trimtokens.anonymizer.strategies import apply

IBAN = "FR1420041010050500013M02606"


def _match(entity: EntityType, value: str, start: int = 0) -> RecognizerMatch:
    return RecognizerMatch(entity, value, start, start + len(value), "test")


# --- Stratégies individuelles -----------------------------------------------


def test_redact() -> None:
    assert RedactStrategy().replacement(_match(EntityType.EMAIL, "a@b.fr")) == "[EMAIL]"


def test_pseudonymize_uses_mapping() -> None:
    strat = PseudonymizeStrategy()
    assert strat.replacement(_match(EntityType.EMAIL, "a@b.fr")) == "[EMAIL_1]"
    assert strat.replacement(_match(EntityType.EMAIL, "a@b.fr")) == "[EMAIL_1]"
    assert len(strat.mapping) == 1


def test_hash_is_deterministic() -> None:
    strat = HashStrategy(length=8)
    r1 = strat.replacement(_match(EntityType.EMAIL, "a@b.fr"))
    r2 = strat.replacement(_match(EntityType.EMAIL, "a@b.fr", start=50))
    assert r1 == r2
    assert r1.startswith("[EMAIL_") and r1.endswith("]")
    assert len(r1) == len("[EMAIL_") + 8 + len("]")


def test_hash_salt_changes_output() -> None:
    base = HashStrategy().replacement(_match(EntityType.EMAIL, "a@b.fr"))
    salted = HashStrategy(salt="x").replacement(_match(EntityType.EMAIL, "a@b.fr"))
    assert base != salted


def test_partial_mask_email() -> None:
    out = PartialMaskStrategy().replacement(_match(EntityType.EMAIL, "jean.dupont@example.fr"))
    assert out == "j***@example.fr"


def test_partial_mask_generic() -> None:
    out = PartialMaskStrategy(keep_start=1, keep_end=2).replacement(_match(EntityType.IBAN, IBAN))
    assert out.startswith("F")
    assert out.endswith("06")
    assert "*" in out
    assert len(out) == len(IBAN)


def test_partial_mask_short_value_fully_masked() -> None:
    out = PartialMaskStrategy(keep_start=2, keep_end=2).replacement(_match(EntityType.PHONE, "12"))
    assert out == "**"


# --- Moteur apply -----------------------------------------------------------


def test_apply_replaces_right_to_left() -> None:
    text = "a@b.fr puis c@d.fr"
    matches = [
        _match(EntityType.EMAIL, "a@b.fr", 0),
        _match(EntityType.EMAIL, "c@d.fr", 12),
    ]
    out = apply(text, matches, RedactStrategy())
    assert out == "[EMAIL] puis [EMAIL]"


# --- Round-trip bout en bout ------------------------------------------------


def test_anonymize_text_default_is_reversible() -> None:
    original = f"Contact a@b.fr, IBAN {IBAN}, tel 06 12 34 56 78."
    result = anonymize_text(original)
    assert isinstance(result, AnonymizationResult)
    assert "a@b.fr" not in result.text
    assert IBAN not in result.text
    assert result.mapping is not None
    assert result.mapping.deanonymize(result.text) == original


def test_anonymize_text_counts() -> None:
    result = anonymize_text(f"a@b.fr et c@d.fr et {IBAN}")
    assert result.counts == {EntityType.EMAIL: 2, EntityType.IBAN: 1}


def test_anonymize_text_redact_has_no_mapping() -> None:
    result = anonymize_text("a@b.fr", strategy=RedactStrategy())
    assert result.text == "[EMAIL]"
    assert result.mapping is None


def test_anonymize_text_shared_mapping_consistency() -> None:
    shared = PseudonymizeStrategy()
    r1 = anonymize_text("a@b.fr ici", strategy=shared)
    r2 = anonymize_text("a@b.fr là", strategy=shared)
    # Même valeur sur deux sections → même tag.
    assert "[EMAIL_1]" in r1.text
    assert "[EMAIL_1]" in r2.text
    assert len(shared.mapping) == 1
