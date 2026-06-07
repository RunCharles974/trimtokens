"""Orchestrateur principal : dispatch extension → extracteur → cleaner → renderer."""

from __future__ import annotations

import importlib
import logging
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from trimtokens.cleaners import clean
from trimtokens.cleaners.steps import StepMetrics, aggregate_metrics
from trimtokens.exceptions import UnsupportedFormatError
from trimtokens.extractors import EXTENSION_MAP
from trimtokens.logging_setup import Events, log_event
from trimtokens.models import (
    ExtractedDocument,
    ExtractOptions,
    ProcessResult,
    Section,
)
from trimtokens.renderer import render
from trimtokens.stats import compute_stats

if TYPE_CHECKING:
    from trimtokens.anonymizer.strategies import Strategy

log = logging.getLogger(__name__)

ExtractorFn = Callable[[Path, ExtractOptions], ExtractedDocument]


def _anonymize_document(
    document: ExtractedDocument,
    options: ExtractOptions,
    strategy: Strategy | None,
) -> tuple[bool, dict[str, int], object | None]:
    """Anonymise en place le contenu des sections de `document`.

    `strategy` partagée (typiquement à travers un lot) assure des pseudonymes
    cohérents entre sections et documents. Si `None`, construite depuis
    `options`. Retourne `(anonymized, counts, mapping)`.
    """
    from trimtokens.anonymizer import (
        PseudonymizeStrategy,
        anonymize_text,
        build_strategy,
        parse_entities,
    )

    active = strategy or build_strategy(options.anon_strategy, salt=options.anon_salt)
    ner_entities = parse_entities(options.anon_entities)
    counts: Counter[str] = Counter()
    for section in document.sections:
        if not section.content.strip():
            continue
        result = anonymize_text(
            section.content,
            strategy=active,
            use_ner=options.anon_ner,
            ner_language=options.anon_ner_languages,
            ner_entities=ner_entities,
            ner_min_score=options.anon_min_score,
        )
        section.content = result.text
        counts.update({k.value: v for k, v in result.counts.items()})

    mapping = active.mapping if isinstance(active, PseudonymizeStrategy) else None
    document.metadata["anonymized"] = True
    document.metadata["anon_counts"] = dict(counts)
    return True, dict(counts), mapping


def _resolve_extractor(ext: str) -> ExtractorFn:
    module_name = EXTENSION_MAP.get(ext.lower())
    if module_name is None:
        raise UnsupportedFormatError(f"Format non supporté : '{ext}'")
    module = importlib.import_module(f"trimtokens.extractors.{module_name}")
    extractor: ExtractorFn = module.extract
    return extractor


def process(
    path: Path,
    options: ExtractOptions | None = None,
    *,
    anon_strategy: Strategy | None = None,
) -> ProcessResult:
    """Pipeline complet : extraction + nettoyage par section + rendu Markdown.

    `anon_strategy` (optionnel) : stratégie d'anonymisation partagée entre
    plusieurs appels `process` pour garantir des pseudonymes cohérents sur tout
    un lot de documents. Ignorée si `options.anonymize` est faux.
    """
    if options is None:
        options = ExtractOptions()

    if not path.exists():
        raise FileNotFoundError(path)

    ext = path.suffix.lower()
    log_event(log, Events.EXTRACTION_START, path=str(path), extension=ext)

    t_start = time.perf_counter()
    try:
        extractor = _resolve_extractor(ext)
        document = extractor(path, options)
    except Exception as exc:
        log_event(
            log,
            Events.EXTRACTION_FAILED,
            path=str(path),
            extension=ext,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    original_size = path.stat().st_size
    original_text = "\n\n".join(s.content for s in document.sections if s.content)
    original_chars = len(original_text)

    cleaned_sections: list[Section] = []
    raw_metrics: list[StepMetrics] = []
    for section in document.sections:
        raw_content = section.content
        if raw_content.strip():
            cleaned_content, _ = clean(
                text=raw_content,
                aggressive=options.aggressive,
                metrics_sink=raw_metrics,
            )
        else:
            cleaned_content = ""
        cleaned_sections.append(
            Section(
                header=section.header,
                content=cleaned_content,
                metadata=section.metadata,
            )
        )
    document.sections = cleaned_sections
    pipeline_metrics = aggregate_metrics(raw_metrics)

    cleaned_full = "\n\n".join(s.content for s in document.sections if s.content)
    stats = compute_stats(
        original_size_bytes=original_size,
        original_chars=original_chars,
        cleaned_text=cleaned_full,
        original_text=original_text,
    )

    anonymized = False
    anon_counts: dict[str, int] = {}
    anon_map: object | None = None
    if options.anonymize:
        anonymized, anon_counts, anon_map = _anonymize_document(document, options, anon_strategy)

    markdown = render(document, stats)
    duration_ms = round((time.perf_counter() - t_start) * 1000, 2)
    log_event(
        log,
        Events.EXTRACTION_COMPLETE,
        path=str(path),
        extension=ext,
        sections=len(document.sections),
        ocr_used=document.ocr_used,
        ocr_pages=len(document.ocr_pages),
        original_chars=original_chars,
        cleaned_chars=stats.cleaned_chars,
        reduction_percent=stats.reduction_percent,
        duration_ms=duration_ms,
    )
    cleaning_ms = round(sum(m.duration_ms for m in pipeline_metrics), 3)
    if pipeline_metrics:
        log_event(
            log,
            Events.PIPELINE_COMPLETE,
            steps=len(pipeline_metrics),
            cleaning_ms=cleaning_ms,
        )
    return ProcessResult(
        document=document,
        stats=stats,
        markdown=markdown,
        pipeline_metrics=list(pipeline_metrics),
        anonymized=anonymized,
        anon_counts=anon_counts,
        anon_map=anon_map,
    )
