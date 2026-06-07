"""Module d'anonymisation TrimTokens.

Détection puis pseudonymisation réversible des données personnelles (PII) dans
les documents confidentiels (contrats, courriers, fiches RH…).

Sous-modules :
- `recognizers` : détection PII par regex FR validées (IBAN, SIRET, NIR, email…).
- `mapping` : table valeur ↔ pseudonyme, réversibilité (JSON + chiffrement).
- `strategies` : redact / pseudonymize / hash / partial-mask + moteur `apply`.
- (à venir) `ner` : reconnaissance d'entités nommées locale (Presidio + spaCy).

Contrainte non-négociable : 100 % local, zéro appel réseau. L'anonymisation
n'est jamais garantie à 100 % — l'appelant doit toujours afficher un rapport
des entités détectées avant export d'un document confidentiel.

Usage rapide :

    result = anonymize_text("IBAN FR14… email a@b.fr")
    result.text     # texte pseudonymisé
    result.mapping  # AnonymizationMap (à chiffrer puis persister)
    result.counts   # {EntityType.IBAN: 1, EntityType.EMAIL: 1}
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from trimtokens.anonymizer import strategies as _strategies
from trimtokens.anonymizer.mapping import (
    AnonymizationMap,
    MappingEntry,
    MappingError,
    merge_maps,
)
from trimtokens.anonymizer.recognizers import (
    DEFAULT_RECOGNIZERS,
    EntityType,
    Recognizer,
    RecognizerMatch,
    find_pii,
    resolve_overlaps,
)
from trimtokens.anonymizer.strategies import (
    HashStrategy,
    PartialMaskStrategy,
    PseudonymizeStrategy,
    RedactStrategy,
    Strategy,
)


@dataclass(frozen=True)
class AnonymizationResult:
    """Résultat d'anonymisation d'un texte.

    `mapping` est `None` pour les stratégies irréversibles (redact, hash,
    partial). `counts` agrège le nombre de PII par type, pour le rapport
    affiché à l'utilisateur avant export.
    """

    text: str
    matches: list[RecognizerMatch] = field(default_factory=list)
    mapping: AnonymizationMap | None = None

    @property
    def counts(self) -> dict[EntityType, int]:
        return dict(Counter(m.entity_type for m in self.matches))


_STRATEGY_NAMES = ("pseudonymize", "redact", "hash", "partial")


def build_strategy(
    name: str,
    *,
    mapping: AnonymizationMap | None = None,
    salt: str = "",
) -> Strategy:
    """Instancie une stratégie par nom.

    `mapping` n'est utilisé que par `pseudonymize` (partage de table pour la
    cohérence multi-documents). `salt` n'est utilisé que par `hash`.
    Lève `ValueError` si `name` est inconnu.
    """
    if name == "pseudonymize":
        return PseudonymizeStrategy(mapping=mapping)
    if name == "redact":
        return RedactStrategy()
    if name == "hash":
        return HashStrategy(salt=salt)
    if name == "partial":
        return PartialMaskStrategy()
    raise ValueError(f"Stratégie d'anonymisation inconnue : '{name}'. Attendu : {_STRATEGY_NAMES}.")


_ENTITY_ALIASES = {
    "personne": EntityType.PERSON,
    "person": EntityType.PERSON,
    "lieu": EntityType.LOCATION,
    "location": EntityType.LOCATION,
    "organisation": EntityType.ORG,
    "organization": EntityType.ORG,
    "org": EntityType.ORG,
}


def parse_entities(spec: str) -> frozenset[EntityType]:
    """Convertit une liste CSV (`"personne,lieu"`) en ensemble d'`EntityType` NER.

    `"all"` → personnes + lieux + organisations. Les noms inconnus sont ignorés.
    Insensible à la casse et aux espaces.
    """
    if spec.strip().lower() == "all":
        return frozenset({EntityType.PERSON, EntityType.LOCATION, EntityType.ORG})
    result: set[EntityType] = set()
    for token in spec.split(","):
        entity = _ENTITY_ALIASES.get(token.strip().lower())
        if entity is not None:
            result.add(entity)
    return frozenset(result)


def detect_all(
    text: str,
    *,
    recognizers: tuple[Recognizer, ...] = DEFAULT_RECOGNIZERS,
    use_ner: bool = False,
    ner_language: str = "fr",
    ner_entities: frozenset[EntityType] | None = None,
    ner_min_score: float = 0.5,
) -> list[RecognizerMatch]:
    """Détecte toutes les PII : regex validées + NER optionnelle, sans chevauchement.

    Les regex (validées arithmétiquement) priment sur les entités NER lors des
    chevauchements. `ner_entities` restreint les types NER (défaut : PERSONNE).
    `ner_min_score` filtre les détections peu confiantes. Si la NER est
    indisponible, retombe silencieusement sur les seules regex.
    """
    matches: list[RecognizerMatch] = []
    for recognizer in recognizers:
        matches.extend(recognizer.finditer(text))
    if use_ner:
        from trimtokens.anonymizer.ner import NER_PRIORITIES, detect_ner

        matches.extend(
            detect_ner(
                text,
                language=ner_language,
                min_score=ner_min_score,
                entities=ner_entities,
            )
        )
        priorities = {r.entity_type: r.priority for r in recognizers}
        priorities.update(NER_PRIORITIES)
        resolved = resolve_overlaps(matches, priorities)
    else:
        resolved = resolve_overlaps(matches)
    return sorted(resolved, key=lambda m: m.start)


def anonymize_text(
    text: str,
    *,
    strategy: Strategy | None = None,
    recognizers: tuple[Recognizer, ...] = DEFAULT_RECOGNIZERS,
    use_ner: bool = False,
    ner_language: str = "fr",
    ner_entities: frozenset[EntityType] | None = None,
    ner_min_score: float = 0.5,
) -> AnonymizationResult:
    """Détecte et substitue les PII de `text`.

    Stratégie par défaut : pseudonymisation réversible. Pour réutiliser une table
    existante (traitement multi-sections / multi-documents cohérent), passer une
    `PseudonymizeStrategy(mapping=...)` partagée. `use_ner=True` ajoute la
    détection NER (défaut : PERSONNE) si l'extra [anonymize] est disponible ;
    `ner_entities`/`ner_min_score` ajustent la portée et la précision.
    """
    if strategy is None:
        strategy = PseudonymizeStrategy()
    matches = detect_all(
        text,
        recognizers=recognizers,
        use_ner=use_ner,
        ner_language=ner_language,
        ner_entities=ner_entities,
        ner_min_score=ner_min_score,
    )
    cleaned = _strategies.apply(text, matches, strategy)
    mapping = strategy.mapping if isinstance(strategy, PseudonymizeStrategy) else None
    return AnonymizationResult(text=cleaned, matches=matches, mapping=mapping)


__all__ = [
    "DEFAULT_RECOGNIZERS",
    "AnonymizationMap",
    "AnonymizationResult",
    "EntityType",
    "HashStrategy",
    "MappingEntry",
    "MappingError",
    "PartialMaskStrategy",
    "PseudonymizeStrategy",
    "Recognizer",
    "RecognizerMatch",
    "RedactStrategy",
    "Strategy",
    "anonymize_text",
    "build_strategy",
    "detect_all",
    "find_pii",
    "merge_maps",
    "parse_entities",
]
