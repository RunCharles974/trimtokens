"""Chargement de la configuration utilisateur TrimTokens.

Hiérarchie :
- Defaults compilés (dataclasses)
- Fichier TOML utilisateur (`~/.trimtokens/config.toml` ou `%APPDATA%\\trimtokens\\config.toml`)
- Override via `TRIMTOKENS_HOME=/chemin`
- Surcharge runtime par les flags CLI / arguments GUI

`load_config()` retourne un `TrimTokensConfig` complet ; `to_extract_options()` le
convertit en `ExtractOptions` consommable par `core.process`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]
from trimtokens.exceptions import ConfigError
from trimtokens.models import ExtractOptions

# --- Paths ----------------------------------------------------------------


def get_home() -> Path:
    """Répertoire de configuration TrimTokens selon l'OS / override env."""
    override = os.environ.get("TRIMTOKENS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "trimtokens"
    return Path.home() / ".trimtokens"


def get_cache_dir() -> Path:
    return get_home() / "cache"


def get_logs_dir() -> Path:
    return get_home() / "logs"


def get_config_path() -> Path:
    return get_home() / "config.toml"


# --- Sections config ------------------------------------------------------


@dataclass
class OCRConfig:
    languages: str = "fra+eng"
    psm: int = 6
    force_ocr: bool = False
    no_ocr: bool = False
    workers: int = 0
    min_dpi: int = 300


@dataclass
class PDFConfig:
    """Seuils heuristiques PDF (cf audit §PDF, externalisation des constantes)."""

    min_native_chars_per_page: int = 50
    ocr_dpi: int = 300
    image_based_max_chars_per_page: int = 100
    image_based_min_images_per_page: int = 2
    image_based_min_pages: int = 3


@dataclass
class CleaningConfig:
    aggressive: bool = False
    max_chars: int = 0
    header_footer_threshold: float = 0.30
    dedup_min_occurrences: int = 3
    drop_empty_pages: bool = True
    empty_page_min_words: int = 5
    merge_continuations: bool = True
    # Filtrage intelligent
    smart_filter: bool = False
    filter_toc: bool = True
    filter_bibliography: bool = True
    filter_sparse: bool = True


@dataclass
class OutputConfig:
    format: str = "md"
    clipboard: bool = False
    open_after: bool = False


@dataclass
class CacheConfig:
    disabled: bool = False
    ttl_days: int = 90


@dataclass
class LoggingConfig:
    level: str = "INFO"
    verbose: bool = False
    # Si défini, écrit en plus un JSON Lines structuré dans ce fichier (append).
    # Utile pour ingestion Loki/ELK/jq. Chemin relatif résolu par rapport au cwd.
    json_file: str = ""


@dataclass
class TrimTokensConfig:
    ocr: OCRConfig = field(default_factory=OCRConfig)
    pdf: PDFConfig = field(default_factory=PDFConfig)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrimTokensConfig:
        """Construit la config depuis un dict (typiquement issu de `tomllib.load`).

        Toute clé inconnue est ignorée silencieusement (forward-compat).
        Toute valeur typée incorrectement lève `ConfigError`.
        """
        try:
            return cls(
                ocr=_build_section(OCRConfig, data.get("ocr", {})),
                pdf=_build_section(PDFConfig, data.get("pdf", {})),
                cleaning=_build_section(CleaningConfig, data.get("cleaning", {})),
                output=_build_section(OutputConfig, data.get("output", {})),
                cache=_build_section(CacheConfig, data.get("cache", {})),
                logging=_build_section(LoggingConfig, data.get("logging", {})),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Configuration invalide : {exc}") from exc

    def to_extract_options(self) -> ExtractOptions:
        """Projette la config sur un `ExtractOptions` consommable par `core.process`."""
        return ExtractOptions(
            ocr_languages=self.ocr.languages,
            ocr_psm=self.ocr.psm,
            no_ocr=self.ocr.no_ocr,
            force_ocr=self.ocr.force_ocr,
            aggressive=self.cleaning.aggressive,
            workers=self.ocr.workers,
            use_cache=not self.cache.disabled,
            max_chars=self.cleaning.max_chars,
            smart_filter=self.cleaning.smart_filter,
            filter_toc=self.cleaning.filter_toc,
            filter_bibliography=self.cleaning.filter_bibliography,
            filter_sparse=self.cleaning.filter_sparse,
            drop_empty_pages=self.cleaning.drop_empty_pages,
            empty_page_min_words=self.cleaning.empty_page_min_words,
            merge_continuations=self.cleaning.merge_continuations,
            pdf_min_native_chars_per_page=self.pdf.min_native_chars_per_page,
            pdf_ocr_dpi=self.pdf.ocr_dpi,
            pdf_image_based_max_chars_per_page=self.pdf.image_based_max_chars_per_page,
            pdf_image_based_min_images_per_page=self.pdf.image_based_min_images_per_page,
            pdf_image_based_min_pages=self.pdf.image_based_min_pages,
        )


def _build_section(cls: type, data: dict[str, Any]) -> Any:
    """Construit une dataclass `cls` depuis `data`, ignorant les clés inconnues."""
    known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known}
    return cls(**filtered)


# --- Loader ---------------------------------------------------------------


def load_config(path: Path | None = None) -> TrimTokensConfig:
    """Charge la configuration TOML.

    - `path` explicite : chemin précis. Lève `ConfigError` si fichier introuvable.
    - `path=None` : utilise `get_config_path()`. Si fichier absent, retourne les
      defaults (silencieux — démarrage zero-config valide).
    - TOML malformé : `ConfigError`.
    """
    target = path if path is not None else get_config_path()

    if not target.exists():
        if path is not None:
            raise ConfigError(f"Fichier de configuration introuvable : {target}")
        return TrimTokensConfig()

    try:
        with target.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML invalide dans '{target}' : {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Impossible de lire '{target}' : {exc}") from exc

    return TrimTokensConfig.from_dict(data)


__all__ = [
    "CacheConfig",
    "CleaningConfig",
    "LoggingConfig",
    "OCRConfig",
    "OutputConfig",
    "PDFConfig",
    "TrimTokensConfig",
    "get_cache_dir",
    "get_config_path",
    "get_home",
    "get_logs_dir",
    "load_config",
]
