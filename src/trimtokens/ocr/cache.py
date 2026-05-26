"""Cache OCR sur disque.

Clé : SHA-256(file_bytes + languages + psm). Stockage : `~/.trimtokens/cache/ocr/<key>.txt`
(ou `%APPDATA%\\.trimtokens\\cache\\ocr\\` sous Windows). Aucun re-OCR pour le même
fichier + paramètres identiques.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from trimtokens.config import get_cache_dir

log = logging.getLogger(__name__)


def compute_cache_key(payload: bytes, languages: str, psm: int) -> str:
    """SHA-256 du payload + paramètres OCR."""
    hasher = hashlib.sha256()
    hasher.update(payload)
    hasher.update(f"|lang={languages}|psm={psm}".encode())
    return hasher.hexdigest()


def compute_file_cache_key(file_path: Path, languages: str, psm: int) -> str:
    """Variante : lit le fichier puis calcule la clé."""
    return compute_cache_key(file_path.read_bytes(), languages, psm)


class OCRCache:
    """Cache disque simple pour résultats OCR."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else (get_cache_dir() / "ocr")
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("Impossible de créer le cache OCR (%s) : %s", self.cache_dir, exc)

    def get(self, key: str) -> str | None:
        """Retourne le texte cached pour `key`, ou None si absent/illisible."""
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            log.debug("Lecture cache OCR échouée (%s) : %s", path, exc)
            return None

    def set(self, key: str, value: str) -> None:
        """Écrit `value` dans le cache pour `key`. Erreurs disque silencieuses."""
        path = self._path_for(key)
        try:
            path.write_text(value, encoding="utf-8")
        except OSError as exc:
            log.debug("Écriture cache OCR échouée (%s) : %s", path, exc)

    def _path_for(self, key: str) -> Path:
        return self.cache_dir / f"{key}.txt"
