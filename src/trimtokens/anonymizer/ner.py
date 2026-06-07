"""Reconnaissance d'entités nommées (NER) locale pour les PII non structurées.

Détecte noms de personnes, organisations et lieux — que les regex ne peuvent
pas attraper. S'appuie sur Microsoft Presidio + spaCy, 100 % local. Tout est
optionnel (extra `[anonymize]`) : sans la dépendance ou sans le modèle spaCy
français, `detect_ner()` retourne une liste vide et journalise un avertissement
unique, sans jamais lever — le pipeline retombe alors sur la détection regex.

Modèle requis (à installer une fois, hors ligne ensuite) :
    python -m spacy download fr_core_news_lg

Seules les entités PERSON / ORGANIZATION / LOCATION sont remontées. Les PII
structurées (email, IBAN, téléphone…) sont volontairement ignorées ici : les
recognizers regex les détectent avec validation arithmétique, plus fiable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from trimtokens.anonymizer.recognizers import EntityType, RecognizerMatch

log = logging.getLogger(__name__)

# Entités NER demandées par défaut : seules les PERSONNES sont des PII fiables.
# Les organisations et lieux génèrent beaucoup de faux positifs sur du texte
# administratif FR (sigles : CSG, Carsat, ASPA…) → opt-in explicite.
DEFAULT_NER_ENTITIES = frozenset({EntityType.PERSON})

# EntityType TrimTokens → type Presidio (pour ne demander que le nécessaire).
_ENTITY_TO_PRESIDIO = {
    EntityType.PERSON: "PERSON",
    EntityType.ORG: "ORGANIZATION",
    EntityType.LOCATION: "LOCATION",
}

# Mots fréquemment mal étiquetés par spaCy FR (civilités, formules, verbes). En
# minuscules. Écartés même si le modèle les classe en PERSONNE/LIEU/ORG : ce ne
# sont jamais des données personnelles. Liste volontairement courte et sûre.
_NOISE_STOPLIST = frozenset(
    {
        "monsieur",
        "madame",
        "mademoiselle",
        "messieurs",
        "mesdames",
        "cher",
        "chère",
        "bonjour",
        "cordialement",
        "merci",
        "regardez",
        "renseignez",
        "payer",
        "code",
    }
)

# Longueur minimale d'une valeur retenue (écarte « G », « NE », initiales isolées).
_MIN_VALUE_LEN = 3

# Modèles spaCy par langue (code court → modèle). Large = meilleur rappel.
_SPACY_MODELS = {
    "fr": "fr_core_news_lg",
    "en": "en_core_web_lg",
}

# Mapping type Presidio → EntityType TrimTokens. Les types absents sont ignorés.
_PRESIDIO_TO_ENTITY = {
    "PERSON": EntityType.PERSON,
    "ORGANIZATION": EntityType.ORG,
    "ORG": EntityType.ORG,
    "LOCATION": EntityType.LOCATION,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
}

# Priorités de résolution des chevauchements pour les entités NER : faibles, afin
# qu'une PII regex validée (IBAN, SIRET…) l'emporte toujours sur une entité NER.
NER_PRIORITIES = {
    EntityType.PERSON: 10,
    EntityType.ORG: 8,
    EntityType.LOCATION: 6,
}

_warned_unavailable = False


@lru_cache(maxsize=4)
def _get_analyzer(language: str) -> Any | None:
    """Construit (et met en cache) un `AnalyzerEngine` Presidio pour `language`.

    Retourne `None` si Presidio, spaCy ou le modèle de langue sont absents.
    Le cache évite de recharger le modèle (~500 Mo) à chaque appel.
    """
    global _warned_unavailable
    model = _SPACY_MODELS.get(language)
    if model is None:
        log.warning("Langue NER non supportée : %s. NER désactivée.", language)
        return None
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        if not _warned_unavailable:
            log.warning(
                "Extra [anonymize] absent : NER désactivée, détection regex seule. "
                "Installer via `pip install trimtokens[anonymize]`."
            )
            _warned_unavailable = True
        return None

    if not spacy.util.is_package(model):
        if not _warned_unavailable:
            log.warning(
                "Modèle spaCy '%s' introuvable : NER désactivée. "
                "Installer via `python -m spacy download %s`.",
                model,
                model,
            )
            _warned_unavailable = True
        return None

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": language, "model_name": model}],
        }
    )
    nlp_engine = provider.create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[language])


def is_ner_available(language: str = "fr") -> bool:
    """Vrai si la NER est opérationnelle pour `language` (deps + modèle présents)."""
    return _get_analyzer(language) is not None


def _is_noise(value: str) -> bool:
    """Vrai si `value` est un faux positif évident (trop court ou mot de la stoplist)."""
    stripped = value.strip()
    if len(stripped) < _MIN_VALUE_LEN:
        return True
    return stripped.lower() in _NOISE_STOPLIST


def detect_ner(
    text: str,
    *,
    language: str = "fr",
    min_score: float = 0.5,
    entities: Iterable[EntityType] | None = None,
) -> list[RecognizerMatch]:
    """Détecte des entités nommées dans `text`.

    `entities` : types à rechercher ; défaut `DEFAULT_NER_ENTITIES` (PERSONNE
    seule, plus fiable). `min_score` filtre les détections Presidio peu
    confiantes. Les valeurs trop courtes ou figurant dans la stoplist (civilités,
    formules) sont écartées. Ne lève jamais : `[]` si la NER est indisponible.
    """
    requested = frozenset(entities) if entities is not None else DEFAULT_NER_ENTITIES
    presidio_entities = [_ENTITY_TO_PRESIDIO[e] for e in requested if e in _ENTITY_TO_PRESIDIO]
    if not presidio_entities:
        return []

    analyzer = _get_analyzer(language)
    if analyzer is None:
        return []
    try:
        results = analyzer.analyze(
            text=text,
            language=language,
            entities=presidio_entities,
        )
    except Exception as exc:  # robustesse : une erreur NER ne casse pas le pipeline
        log.warning("Échec NER (ignoré, fallback regex) : %s", exc)
        return []

    matches: list[RecognizerMatch] = []
    for r in results:
        if r.score < min_score:
            continue
        entity_type = _PRESIDIO_TO_ENTITY.get(r.entity_type)
        if entity_type is None or entity_type not in requested:
            continue
        value = text[r.start : r.end]
        if _is_noise(value):
            continue
        matches.append(
            RecognizerMatch(
                entity_type=entity_type,
                value=value,
                start=r.start,
                end=r.end,
                recognizer="ner",
            )
        )
    return matches


__all__ = [
    "DEFAULT_NER_ENTITIES",
    "NER_PRIORITIES",
    "detect_ner",
    "is_ner_available",
]
