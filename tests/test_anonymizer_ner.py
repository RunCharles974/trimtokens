"""Tests des helpers NER ne nécessitant pas le modèle spaCy (filtre, parsing).

La NER complète (Presidio + `fr_core_news_lg`) n'est pas testée ici : le modèle
pèse ~500 Mo et n'est pas une dépendance de test. On couvre la logique pure :
parsing des entités, filtre anti-bruit, court-circuit quand la liste est vide.
"""

from __future__ import annotations

from trimtokens.anonymizer import parse_entities
from trimtokens.anonymizer.ner import (
    DEFAULT_NER_ENTITIES,
    _is_noise,
    detect_ner,
)
from trimtokens.anonymizer.recognizers import EntityType


def test_default_entities_is_person_only() -> None:
    assert frozenset({EntityType.PERSON}) == DEFAULT_NER_ENTITIES


def test_parse_entities_csv() -> None:
    assert parse_entities("personne") == frozenset({EntityType.PERSON})
    assert parse_entities("personne,lieu") == {EntityType.PERSON, EntityType.LOCATION}
    assert parse_entities(" Lieu , Organisation ") == {EntityType.LOCATION, EntityType.ORG}


def test_parse_entities_all() -> None:
    assert parse_entities("all") == {EntityType.PERSON, EntityType.LOCATION, EntityType.ORG}


def test_parse_entities_ignores_unknown() -> None:
    assert parse_entities("personne,bogus") == frozenset({EntityType.PERSON})
    assert parse_entities("rien") == frozenset()


def test_is_noise_short_values() -> None:
    assert _is_noise("G")
    assert _is_noise("NE")
    assert _is_noise("  x ")
    assert not _is_noise("Dupont")


def test_is_noise_stoplist() -> None:
    assert _is_noise("Monsieur")
    assert _is_noise("madame")
    assert _is_noise("Cordialement")
    assert not _is_noise("Philippe")


def test_detect_ner_empty_entities_short_circuits() -> None:
    # Aucune entité demandée → retourne [] sans charger le modèle.
    assert detect_ner("Texte avec Jean Dupont", entities=frozenset()) == []
