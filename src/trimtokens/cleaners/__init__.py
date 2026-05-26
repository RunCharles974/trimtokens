"""Pipeline de nettoyage textuel.

Deux APIs coexistent :

- **Fonctionnelle** (`clean`, `normalize_unicode`, …) — historique, simple, stable.
- **Orientée étapes** (`Pipeline`, `CleaningStep`, `StepMetrics`, `default_pipeline`)
  — permet activation/désactivation par étape, profiling fin et extension plugin.

`clean()` délègue à `Pipeline` en interne ; les deux APIs produisent le même résultat.
"""

from __future__ import annotations

from trimtokens.cleaners.pipeline import (
    clean,
    collapse_whitespace,
    convert_ligatures,
    dedup_paragraphs,
    finalize,
    limit_consecutive_newlines,
    normalize_unicode,
    rejoin_hyphenated,
    strip_invisibles,
    strip_punctuation_only_lines,
    strip_recurring_headers_footers,
)
from trimtokens.cleaners.steps import (
    CleaningStep,
    CollapseWhitespaceStep,
    ConvertLigaturesStep,
    DedupParagraphsStep,
    FinalizeStep,
    LimitConsecutiveNewlinesStep,
    NormalizeUnicodeStep,
    Pipeline,
    RejoinHyphenatedStep,
    StepMetrics,
    StripInvisiblesStep,
    StripPunctuationOnlyLinesStep,
    default_pipeline,
)

__all__ = [
    "CleaningStep",
    "CollapseWhitespaceStep",
    "ConvertLigaturesStep",
    "DedupParagraphsStep",
    "FinalizeStep",
    "LimitConsecutiveNewlinesStep",
    "NormalizeUnicodeStep",
    "Pipeline",
    "RejoinHyphenatedStep",
    "StepMetrics",
    "StripInvisiblesStep",
    "StripPunctuationOnlyLinesStep",
    "clean",
    "collapse_whitespace",
    "convert_ligatures",
    "dedup_paragraphs",
    "default_pipeline",
    "finalize",
    "limit_consecutive_newlines",
    "normalize_unicode",
    "rejoin_hyphenated",
    "strip_invisibles",
    "strip_punctuation_only_lines",
    "strip_recurring_headers_footers",
]
