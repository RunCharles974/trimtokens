"""Stratégies de substitution des PII détectées.

Une stratégie transforme une `RecognizerMatch` en chaîne de remplacement. Quatre
variantes (cf plan v0.2) :

- `PseudonymizeStrategy` — `[EMAIL_1]`, cohérent et **réversible** via une
  `AnonymizationMap` (défaut pour les contrats).
- `RedactStrategy` — `[EMAIL]`, irréversible, sans table.
- `HashStrategy` — `[EMAIL_a3f91c2b]`, déterministe et stable inter-documents.
- `PartialMaskStrategy` — masquage partiel (`j***@example.fr`), garde un repère
  visuel sans révéler la valeur.

Le moteur `apply()` réécrit le texte de droite à gauche pour que les offsets des
correspondances restent valides pendant le remplacement.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from trimtokens.anonymizer.mapping import AnonymizationMap
from trimtokens.anonymizer.recognizers import RecognizerMatch


@runtime_checkable
class Strategy(Protocol):
    """Contrat d'une stratégie d'anonymisation."""

    name: str

    def replacement(self, match: RecognizerMatch) -> str:
        """Retourne la chaîne qui remplacera `match.value` dans le texte."""
        ...


class PseudonymizeStrategy:
    """Remplace par un pseudonyme stable, réversible via la table fournie.

    La table (`AnonymizationMap`) accumule les correspondances ; après `apply`,
    l'appelant la persiste (`save_encrypted`) pour pouvoir ré-identifier.
    """

    name = "pseudonymize"

    def __init__(self, mapping: AnonymizationMap | None = None) -> None:
        self.mapping = mapping if mapping is not None else AnonymizationMap()

    def replacement(self, match: RecognizerMatch) -> str:
        return self.mapping.pseudonym(match.entity_type, match.value)


class RedactStrategy:
    """Remplace par le seul type d'entité, sans table : `[EMAIL]`. Irréversible."""

    name = "redact"

    def replacement(self, match: RecognizerMatch) -> str:
        return f"[{match.entity_type.value}]"


class HashStrategy:
    """Remplace par un hash tronqué déterministe : `[EMAIL_a3f91c2b]`.

    Stable inter-documents (même valeur → même tag partout), utile pour corréler
    sans révéler. `salt` optionnel pour contrer les attaques par dictionnaire ;
    un salt fixe préserve la stabilité inter-documents, un salt aléatoire la rompt.
    """

    name = "hash"

    def __init__(self, salt: str = "", length: int = 8) -> None:
        self.salt = salt
        self.length = length

    def replacement(self, match: RecognizerMatch) -> str:
        digest = hashlib.sha256((self.salt + match.value).encode("utf-8")).hexdigest()
        return f"[{match.entity_type.value}_{digest[: self.length]}]"


class PartialMaskStrategy:
    """Masque le milieu en conservant des caractères de repère.

    E-mails traités à part (`j***@example.fr`). Sinon, conserve `keep_start`
    premiers et `keep_end` derniers caractères *significatifs* (hors espaces),
    le reste devient `mask_char`.
    """

    name = "partial"

    def __init__(self, keep_start: int = 1, keep_end: int = 2, mask_char: str = "*") -> None:
        self.keep_start = keep_start
        self.keep_end = keep_end
        self.mask_char = mask_char

    def replacement(self, match: RecognizerMatch) -> str:
        value = match.value
        if "@" in value:
            local, _, domain = value.partition("@")
            head = local[:1] if local else ""
            return f"{head}{self.mask_char * 3}@{domain}"
        significant = [i for i, c in enumerate(value) if not c.isspace()]
        if len(significant) <= self.keep_start + self.keep_end:
            return self.mask_char * len(value)
        reveal = set(significant[: self.keep_start] + significant[-self.keep_end :])
        return "".join(
            c if (i in reveal or c.isspace()) else self.mask_char for i, c in enumerate(value)
        )


def apply(text: str, matches: list[RecognizerMatch], strategy: Strategy) -> str:
    """Remplace chaque correspondance dans `text` selon `strategy`.

    Réécrit de droite à gauche : remplacer une correspondance ne décale pas les
    offsets de celles situées plus à gauche, encore à traiter. Suppose les
    correspondances non chevauchantes (garanti par `find_pii`).
    """
    ordered = sorted(matches, key=lambda m: m.start, reverse=True)
    for m in ordered:
        text = text[: m.start] + strategy.replacement(m) + text[m.end :]
    return text


__all__ = [
    "HashStrategy",
    "PartialMaskStrategy",
    "PseudonymizeStrategy",
    "RedactStrategy",
    "Strategy",
    "apply",
]
