"""Table de correspondance valeur ↔ pseudonyme (réversibilité).

Cœur de la pseudonymisation : à chaque valeur PII détectée on associe un
pseudonyme stable et unique au niveau du document (`Jean Dupont`→`[PERSONNE_1]`,
toutes ses occurrences partageant le même tag). La table permet la
ré-identification *locale* via `deanonymize()` — on envoie le Markdown
pseudonymisé à Claude, puis on restaure les valeurs réelles dans sa réponse.

Sécurité : la table contient les données sensibles en clair. Elle ne doit
**jamais** être incluse dans le document de sortie. `save_json` produit un
fichier séparé ; `save_encrypted` le chiffre (Fernet, clé dérivée scrypt) si
l'extra `[anonymize]` fournit `cryptography`. Sans cette dépendance,
`save_encrypted` lève `MissingDependencyError` plutôt que d'écrire en clair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from trimtokens.anonymizer.recognizers import EntityType
from trimtokens.exceptions import MissingDependencyError, TrimTokensError

if TYPE_CHECKING:
    from collections.abc import Iterable

_FORMAT_VERSION = 1


class MappingError(TrimTokensError):
    """Erreur de (dé)sérialisation ou de déchiffrement d'une table de mapping."""


@dataclass(frozen=True)
class MappingEntry:
    """Une association persistée : pseudonyme ↔ valeur réelle + son type."""

    tag: str
    entity_type: EntityType
    value: str


@dataclass
class AnonymizationMap:
    """Table bidirectionnelle valeur ↔ pseudonyme, à l'échelle d'un document.

    Stateful : `pseudonym()` assigne un nouveau tag à la première rencontre
    d'une valeur, et le réutilise ensuite. Les compteurs sont par type d'entité
    (`[EMAIL_1]`, `[EMAIL_2]`, `[IBAN_1]`…).
    """

    _forward: dict[str, str] = field(default_factory=dict)  # value -> tag
    _reverse: dict[str, MappingEntry] = field(default_factory=dict)  # tag -> entry
    _counters: dict[EntityType, int] = field(default_factory=dict)

    def pseudonym(self, entity_type: EntityType, value: str) -> str:
        """Retourne le pseudonyme de `value`, en en créant un si nécessaire.

        Idempotent : deux appels avec la même `value` renvoient le même tag.
        """
        existing = self._forward.get(value)
        if existing is not None:
            return existing
        count = self._counters.get(entity_type, 0) + 1
        self._counters[entity_type] = count
        tag = f"[{entity_type.value}_{count}]"
        self._forward[value] = tag
        self._reverse[tag] = MappingEntry(tag=tag, entity_type=entity_type, value=value)
        return tag

    def __len__(self) -> int:
        return len(self._reverse)

    def entries(self) -> list[MappingEntry]:
        """Entrées dans l'ordre d'insertion (stable depuis Python 3.7)."""
        return list(self._reverse.values())

    def deanonymize(self, text: str) -> str:
        """Restaure les valeurs réelles à partir des pseudonymes présents dans `text`.

        Remplace les tags du plus long au plus court pour éviter qu'un préfixe
        (`[EMAIL_1]`) n'altère un tag plus long (`[EMAIL_12]`). Les crochets
        fermants rendent ce risque théorique, mais l'ordre garantit la robustesse.
        """
        for tag in sorted(self._reverse, key=len, reverse=True):
            text = text.replace(tag, self._reverse[tag].value)
        return text

    # --- Sérialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "version": _FORMAT_VERSION,
            "entries": [
                {"tag": e.tag, "type": e.entity_type.value, "value": e.value}
                for e in self.entries()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AnonymizationMap:
        raw_entries = data.get("entries")
        if not isinstance(raw_entries, list):
            raise MappingError("Table de mapping invalide : clé 'entries' absente ou malformée.")
        instance = cls()
        for item in raw_entries:
            if not isinstance(item, dict):
                raise MappingError("Entrée de mapping malformée.")
            try:
                entity_type = EntityType(item["type"])
                entry = MappingEntry(
                    tag=str(item["tag"]),
                    entity_type=entity_type,
                    value=str(item["value"]),
                )
            except (KeyError, ValueError) as exc:
                raise MappingError(f"Entrée de mapping invalide : {item!r}") from exc
            instance._reverse[entry.tag] = entry
            instance._forward[entry.value] = entry.tag
            instance._counters[entity_type] = self_count(instance, entity_type)
        return instance

    def save_json(self, path: Path) -> None:
        """Écrit la table en JSON clair. Fichier sensible — à protéger/supprimer.

        Préférer `save_encrypted` pour des documents confidentiels.
        """
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load_json(cls, path: Path) -> AnonymizationMap:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MappingError(f"Lecture de la table impossible : {path}") from exc
        if not isinstance(data, dict):
            raise MappingError("Racine JSON de mapping attendue : objet.")
        return cls.from_dict(data)

    # --- Chiffrement optionnel (extra [anonymize]) -------------------------

    def save_encrypted(self, path: Path, passphrase: str) -> None:
        """Chiffre la table avec une clé dérivée de `passphrase` (Fernet/scrypt).

        Lève `MissingDependencyError` si `cryptography` n'est pas installé.
        Format fichier : `salt (16 octets) || jeton Fernet`.
        """
        fernet, salt = _build_fernet(passphrase)
        payload = json.dumps(self.to_dict(), ensure_ascii=False).encode("utf-8")
        token = fernet.encrypt(payload)
        path.write_bytes(salt + token)

    @classmethod
    def load_encrypted(cls, path: Path, passphrase: str) -> AnonymizationMap:
        """Déchiffre une table produite par `save_encrypted`.

        Lève `MappingError` si la passphrase est fausse ou le fichier corrompu.
        """
        blob = path.read_bytes()
        if len(blob) < 17:
            raise MappingError("Fichier de mapping chiffré tronqué.")
        salt, token = blob[:16], blob[16:]
        fernet, _ = _build_fernet(passphrase, salt=salt)
        try:
            payload = fernet.decrypt(token)
        except Exception as exc:  # InvalidToken et dérivés
            raise MappingError("Déchiffrement impossible : passphrase erronée ou fichier altéré.") from exc
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise MappingError("Contenu déchiffré inattendu.")
        return cls.from_dict(data)


def self_count(instance: AnonymizationMap, entity_type: EntityType) -> int:
    """Compte les tags déjà présents pour `entity_type` (reconstruit les compteurs)."""
    return sum(1 for e in instance._reverse.values() if e.entity_type is entity_type)


def merge_maps(maps: Iterable[AnonymizationMap]) -> AnonymizationMap:
    """Fusionne plusieurs tables (ex. traitement par lots) en réassignant les tags.

    Conserve la cohérence valeur→tag : une valeur vue dans plusieurs documents
    obtient un unique pseudonyme global.
    """
    merged = AnonymizationMap()
    for source in maps:
        for entry in source.entries():
            merged.pseudonym(entry.entity_type, entry.value)
    return merged


def _build_fernet(passphrase: str, *, salt: bytes | None = None) -> tuple[Any, bytes]:
    """Construit un objet Fernet à partir d'une passphrase (KDF scrypt).

    `scrypt` vient de la stdlib (`hashlib`) ; seul `cryptography.Fernet` est une
    dépendance optionnelle. Retourne `(fernet, salt)`.
    """
    import base64
    import hashlib
    import os

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise MissingDependencyError(
            "Le chiffrement de la table requiert l'extra [anonymize] "
            "(`pip install trimtokens[anonymize]`)."
        ) from exc

    if salt is None:
        salt = os.urandom(16)
    derived = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key), salt


__all__ = [
    "AnonymizationMap",
    "MappingEntry",
    "MappingError",
    "merge_maps",
]
