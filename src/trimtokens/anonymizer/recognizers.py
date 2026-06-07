"""Détection de données personnelles (PII) par regex françaises validées.

Première brique de l'anonymisation (cf plan v0.2). Détecte les PII *structurées*
— celles qui suivent un format déterministe : email, téléphone FR, IBAN, SIREN,
SIRET, n° de TVA intracommunautaire, NIR (sécurité sociale), carte bancaire,
plaque d'immatriculation. Les entités *non structurées* (noms de personnes, de
sociétés, lieux) relèvent de la NER (sous-module `ner`, à venir).

Principe : chaque `Recognizer` combine une regex (rappel) et un *validateur*
optionnel (précision). Le validateur applique la règle arithmétique du format
(Luhn, modulo 97, clé de contrôle NIR) pour écarter les faux positifs — crucial
sur des documents confidentiels où un faux négatif est une fuite et un faux
positif dégrade le texte. Une suite de 14 chiffres n'est retenue comme SIRET que
si sa clé de Luhn est correcte.

Aucune dépendance externe : `re` + `unicodedata` suffisent. Module importable
sans l'extra `[anonymize]`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Final


class EntityType(str, Enum):
    """Catégories de PII détectables. La valeur sert de préfixe de pseudonyme.

    Hérite de `str` pour un usage transparent en clé de dict / formatage
    (`f"[{entity}_1]"` → `[EMAIL_1]`).
    """

    EMAIL = "EMAIL"
    PHONE = "TELEPHONE"
    IBAN = "IBAN"
    SIREN = "SIREN"
    SIRET = "SIRET"
    VAT = "TVA"
    NIR = "NIR"
    CREDIT_CARD = "CARTE_BANCAIRE"
    LICENSE_PLATE = "IMMATRICULATION"
    # Entités non structurées — produites par la NER (sous-module `ner`), pas par
    # les regex. Pas de validateur arithmétique possible.
    PERSON = "PERSONNE"
    ORG = "ORGANISATION"
    LOCATION = "LIEU"

    def __str__(self) -> str:  # pragma: no cover - confort d'affichage
        return self.value


@dataclass(frozen=True)
class RecognizerMatch:
    """Occurrence de PII localisée dans un texte.

    `value` est la sous-chaîne exacte (telle qu'écrite dans le document, espaces
    et séparateurs inclus) ; `start`/`end` sont des offsets caractères sur le
    texte d'origine (`text[start:end] == value`).
    """

    entity_type: EntityType
    value: str
    start: int
    end: int
    recognizer: str

    def __len__(self) -> int:
        return self.end - self.start


# --- Validateurs (précision) ---------------------------------------------


def _luhn_ok(digits: str) -> bool:
    """Vrai si `digits` (chiffres uniquement) satisfait la clé de Luhn.

    Utilisé pour SIREN (9), SIRET (14) et cartes bancaires (13–19).
    """
    if not digits.isdigit():
        return False
    total = 0
    # Double un chiffre sur deux en partant de la droite.
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_ok(raw: str) -> bool:
    """Vrai si `raw` est un IBAN valide (contrôle modulo 97 == 1, ISO 7064).

    Tolère les espaces de regroupement. Longueur FR attendue : 27 caractères.
    """
    compact = raw.replace(" ", "").upper()
    if len(compact) < 15 or len(compact) > 34:
        return False
    if not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    # Déplace les 4 premiers caractères à la fin, puis convertit lettres → nombres.
    rearranged = compact[4:] + compact[:4]
    digits = []
    for char in rearranged:
        if char.isdigit():
            digits.append(char)
        elif char.isalpha():
            digits.append(str(ord(char) - 55))  # A=10 … Z=35
        else:
            return False
    return int("".join(digits)) % 97 == 1


def _nir_ok(raw: str) -> bool:
    """Vrai si `raw` est un NIR (n° sécurité sociale FR) avec clé valide.

    Structure : 13 chiffres + clé de 2 chiffres. La clé vaut
    `97 - (NIR mod 97)`. Gère la Corse (`2A`→19, `2B`→18) sur le département.
    """
    compact = raw.replace(" ", "").upper()
    if len(compact) != 15:
        return False
    body, key = compact[:13], compact[13:]
    if not key.isdigit():
        return False
    # Département corse : 6e–7e caractères peuvent être 2A / 2B.
    corse = body[5:7]
    if corse == "2A":
        body = body[:5] + "19" + body[7:]
    elif corse == "2B":
        body = body[:5] + "18" + body[7:]
    if not body.isdigit():
        return False
    return int(key) == 97 - (int(body) % 97)


def _vat_fr_ok(raw: str) -> bool:
    """Vrai si `raw` est un n° de TVA intracommunautaire FR valide.

    Format : `FR` + clé (2 chiffres) + SIREN (9 chiffres, Luhn).
    Clé = `(12 + 3 * (SIREN mod 97)) mod 97`.
    """
    compact = raw.replace(" ", "").upper()
    if len(compact) != 13 or not compact.startswith("FR"):
        return False
    key, siren = compact[2:4], compact[4:]
    if not key.isdigit() or not siren.isdigit():
        return False
    if not _luhn_ok(siren):
        return False
    return int(key) == (12 + 3 * (int(siren) % 97)) % 97


# --- Définition d'un recognizer ------------------------------------------


@dataclass(frozen=True)
class Recognizer:
    """Détecteur d'un type de PII : regex + validateur optionnel.

    `priority` arbitre les chevauchements (cf `find_pii`) : à offset égal, le
    recognizer de plus forte priorité l'emporte. SIRET (14) > SIREN (9) pour
    éviter qu'un SIRET soit tronqué en SIREN.
    """

    entity_type: EntityType
    name: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    priority: int = 0

    def finditer(self, text: str) -> list[RecognizerMatch]:
        """Retourne toutes les occurrences validées dans `text`."""
        matches: list[RecognizerMatch] = []
        for m in self.pattern.finditer(text):
            value = m.group()
            if self.validator is not None and not self.validator(value):
                continue
            matches.append(
                RecognizerMatch(
                    entity_type=self.entity_type,
                    value=value,
                    start=m.start(),
                    end=m.end(),
                    recognizer=self.name,
                )
            )
        return matches


# --- Patterns FR ----------------------------------------------------------
# `(?<!\w)` / `(?!\w)` : ancres de mot tolérant la ponctuation, contrairement à
# `\b` qui se comporte mal autour des `+`, `.` et chiffres collés.

_EMAIL_RE: Final = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"
)

# Téléphone FR : +33 / 0033 / 0, puis 9 chiffres, séparateurs espace/point/tiret.
_PHONE_RE: Final = re.compile(
    r"(?<![\w+])(?:(?:\+|00)33\s?(?:\(0\)\s?)?|0)\d(?:[\s.\-]?\d{2}){4}(?!\d)"
)

# IBAN : 2 lettres pays + 2 chiffres clé + 11–30 alphanum, groupés par 4.
_IBAN_RE: Final = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{1,4}){2,8}(?![A-Za-z0-9])"
)

# SIREN/SIRET : 9 ou 14 chiffres, séparateurs espace optionnels (groupes 3/3/3[/5]).
_SIRET_RE: Final = re.compile(r"(?<!\d)\d{3}[\s]?\d{3}[\s]?\d{3}[\s]?\d{5}(?!\d)")
_SIREN_RE: Final = re.compile(r"(?<!\d)\d{3}[\s]?\d{3}[\s]?\d{3}(?!\d)")

_VAT_RE: Final = re.compile(r"(?<![A-Za-z0-9])FR\s?[0-9A-Z]{2}\s?\d{3}\s?\d{3}\s?\d{3}(?![A-Za-z0-9])")

# NIR : sexe(1) année(2) mois(2) dépt(2, incl. 2A/2B) commune(3) ordre(3) clé(2).
_NIR_RE: Final = re.compile(
    r"(?<!\d)[12]\s?\d{2}\s?\d{2}\s?(?:\d{2}|2[AB])\s?\d{3}\s?\d{3}\s?\d{2}(?!\d)"
)

# Carte bancaire : 13–19 chiffres groupés par 4, validés par Luhn.
_CREDIT_CARD_RE: Final = re.compile(r"(?<!\d)(?:\d{4}[\s-]?){3}\d{1,7}(?!\d)")

# Plaque SIV (depuis 2009) : AA-123-AA (séparateurs espace/tiret tolérés).
_LICENSE_PLATE_RE: Final = re.compile(
    r"(?<![A-Za-z0-9])[A-HJ-NP-TV-Z]{2}[\s-]?\d{3}[\s-]?[A-HJ-NP-TV-Z]{2}(?![A-Za-z0-9])"
)


def _credit_card_ok(raw: str) -> bool:
    digits = re.sub(r"[\s-]", "", raw)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _siren_ok(raw: str) -> bool:
    return _luhn_ok(re.sub(r"\s", "", raw))


DEFAULT_RECOGNIZERS: Final[tuple[Recognizer, ...]] = (
    Recognizer(EntityType.EMAIL, "email", _EMAIL_RE, priority=90),
    Recognizer(EntityType.IBAN, "iban", _IBAN_RE, _iban_ok, priority=80),
    Recognizer(EntityType.VAT, "tva_fr", _VAT_RE, _vat_fr_ok, priority=75),
    Recognizer(EntityType.NIR, "nir", _NIR_RE, _nir_ok, priority=70),
    # SIRET avant CARTE_BANCAIRE : un nombre de 14 chiffres à clé de Luhn valide
    # satisfait les deux formats (le SIRET utilise Luhn). Dans un document
    # d'affaires FR, c'est quasi toujours un SIRET — il l'emporte au chevauchement.
    Recognizer(EntityType.SIRET, "siret", _SIRET_RE, lambda r: _luhn_ok(re.sub(r"\s", "", r)), 66),
    Recognizer(
        EntityType.CREDIT_CARD, "carte_bancaire", _CREDIT_CARD_RE, _credit_card_ok, priority=65
    ),
    Recognizer(EntityType.SIREN, "siren", _SIREN_RE, _siren_ok, priority=50),
    Recognizer(EntityType.PHONE, "telephone_fr", _PHONE_RE, priority=40),
    Recognizer(EntityType.LICENSE_PLATE, "immatriculation", _LICENSE_PLATE_RE, priority=30),
)


# --- Résolution des chevauchements ---------------------------------------


_DEFAULT_PRIORITIES: Final = {r.entity_type: r.priority for r in DEFAULT_RECOGNIZERS}


def resolve_overlaps(
    matches: list[RecognizerMatch],
    priorities: dict[EntityType, int] | None = None,
) -> list[RecognizerMatch]:
    """Écarte les correspondances qui se chevauchent.

    Garde, à chevauchement, la plus longue ; à longueur égale, la plus
    prioritaire. Empêche par exemple qu'un SIRET (14 chiffres) soit aussi compté
    comme SIREN (ses 9 premiers chiffres), ou qu'une entité NER (`PERSONNE`,
    priorité faible) écrase un IBAN validé. `priorities` permet de mêler regex et
    NER ; à défaut, priorités des recognizers regex (NER → 0).
    """
    prio = priorities if priorities is not None else _DEFAULT_PRIORITIES

    def sort_key(m: RecognizerMatch) -> tuple[int, int, int]:
        return (m.start, -len(m), -prio.get(m.entity_type, 0))

    ordered = sorted(matches, key=sort_key)
    kept: list[RecognizerMatch] = []
    occupied_end = -1
    for m in ordered:
        if m.start >= occupied_end:
            kept.append(m)
            occupied_end = m.end
    return kept


def find_pii(
    text: str,
    recognizers: tuple[Recognizer, ...] = DEFAULT_RECOGNIZERS,
) -> list[RecognizerMatch]:
    """Détecte les PII structurées dans `text`, chevauchements résolus.

    Retourne les correspondances triées par position d'apparition. Détection
    seule : ni masquage, ni mapping — c'est le rôle des sous-modules
    `strategies` et `mapping` (à venir).
    """
    found: list[RecognizerMatch] = []
    for recognizer in recognizers:
        found.extend(recognizer.finditer(text))
    resolved = resolve_overlaps(found)
    return sorted(resolved, key=lambda m: m.start)


__all__ = [
    "DEFAULT_RECOGNIZERS",
    "EntityType",
    "Recognizer",
    "RecognizerMatch",
    "find_pii",
    "resolve_overlaps",
]
