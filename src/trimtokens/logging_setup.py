"""Logging structuré pour TrimTokens (cf audit §Robustesse "Logging structuré").

Deux canaux :

- **Console** (RichHandler) : sortie humaine, format compact, niveau réglable.
- **Fichier JSON Lines** (opt-in) : sortie machine, un objet JSON par ligne,
  parsable par jq / Loki / ELK / pandas.

API ergonomique :

    from trimtokens.logging_setup import log_event
    log_event(log, "ocr_complete", pages=12, duration_ms=4210, cache_hits=3)

→ Console : `ocr_complete pages=12 duration_ms=4210 cache_hits=3`
→ JSON    : `{"ts": "...", "level": "INFO", "logger": "...", "event": "ocr_complete",
              "data": {"pages": 12, "duration_ms": 4210, "cache_hits": 3}}`

`log_event` reste compatible avec les call sites historiques `log.info("msg", arg)`
puisqu'il n'est utilisé qu'aux nouveaux points d'observabilité. L'ancien format
printf-style continue de fonctionner via RichHandler.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

# Clé utilisée dans `LogRecord` pour transporter les champs structurés.
_EVENT_FIELD = "event_data"


class JSONFormatter(logging.Formatter):
    """Formatter JSON Lines : un objet par enregistrement, sérialisable.

    Schéma :
        {
            "ts":      "2026-05-26T13:42:18.123456+00:00",   # ISO 8601 UTC
            "level":   "INFO",
            "logger":  "trimtokens.extractors.pdf",
            "event":   "ocr_complete",                        # = record.msg
            "data":    { "pages": 12, "duration_ms": 4210 },  # = record.event_data
            "module":  "pdf",
            "exc":     "...",                                 # si exc_info présent
        }
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "module": record.module,
        }

        data = getattr(record, _EVENT_FIELD, None)
        if isinstance(data, dict) and data:
            payload["data"] = data

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleStructuredFormatter(logging.Formatter):
    """Formatter console : affiche `event_data` en suffixe `k=v` lisible.

    Si `event_data` absent, retombe sur le message brut (compat call sites
    historiques `log.info("texte %s", arg)`).
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        data = getattr(record, _EVENT_FIELD, None)
        if isinstance(data, dict) and data:
            extras = " ".join(f"{k}={v}" for k, v in data.items())
            return f"{base} {extras}" if base else extras
        return base


def log_event(logger: logging.Logger, event: str, /, **fields: Any) -> None:
    """Émet un événement structuré.

    `event` est un identifiant snake_case stable (ex `ocr_complete`,
    `cache_hit`, `extraction_failed`) — sert de clé d'agrégation côté observabilité.
    `fields` est sérialisé JSON dans le canal fichier, et affiché `k=v` en console.
    """
    logger.info(event, extra={_EVENT_FIELD: dict(fields)})


def setup_logging(
    *,
    level: int = logging.WARNING,
    console: bool = True,
    json_file: Path | None = None,
    err_console: Console | None = None,
) -> None:
    """Configure le logging racine TrimTokens.

    - `level` : seuil global appliqué aux deux handlers.
    - `console=True` : ajoute un RichHandler (stderr par défaut). `err_console`
      permet d'injecter une `rich.Console` custom (utilisé par la CLI).
    - `json_file` : si fourni, ajoute un FileHandler JSON Lines (append, utf-8).
      Le répertoire parent est créé si nécessaire.

    `force=True` interne : réinitialise les handlers existants pour éviter les
    doublons quand la CLI est invoquée plusieurs fois dans un même process.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level)

    if console:
        console_target = err_console if err_console is not None else Console(stderr=True)
        rich_handler = RichHandler(
            console=console_target,
            show_path=False,
            show_time=False,
            rich_tracebacks=False,
        )
        rich_handler.setLevel(level)
        rich_handler.setFormatter(ConsoleStructuredFormatter(fmt="%(message)s"))
        root.addHandler(rich_handler)

    if json_file is not None:
        json_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(json_file, mode="a", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(JSONFormatter())
        root.addHandler(file_handler)


def teardown_logging() -> None:
    """Ferme et retire tous les handlers root. Utile pour les tests."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        with contextlib.suppress(Exception):  # pragma: no cover - best effort cleanup
            handler.close()
        root.removeHandler(handler)


# Export d'identifiants standardisés d'événements (évite typos).
class Events:
    """Catalogue des événements structurés émis par le pipeline.

    Centralisé pour éviter les divergences typographiques entre call sites et
    consommateurs (dashboards, alerting). Ajouter ici puis utiliser via
    `log_event(log, Events.OCR_COMPLETE, ...)`.
    """

    EXTRACTION_START = "extraction_start"
    EXTRACTION_COMPLETE = "extraction_complete"
    EXTRACTION_FAILED = "extraction_failed"
    OCR_START = "ocr_start"
    OCR_COMPLETE = "ocr_complete"
    OCR_SKIPPED = "ocr_skipped"
    CACHE_HIT = "ocr_cache_hit"
    CACHE_MISS = "ocr_cache_miss"
    PIPELINE_COMPLETE = "cleaning_pipeline_complete"


__all__ = [
    "ConsoleStructuredFormatter",
    "Events",
    "JSONFormatter",
    "log_event",
    "setup_logging",
    "teardown_logging",
]
