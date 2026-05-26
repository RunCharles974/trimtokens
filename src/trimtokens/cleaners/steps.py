"""Pipeline orienté étapes (plugin pattern).

Chaque étape implémente le Protocol `CleaningStep` (`name`, `apply(text)->text`).
Une `Pipeline` exécute une séquence d'étapes et retourne (texte_final, métriques).
Cf audit §"Pipeline orienté objets" : permet activation/désactivation par étape,
profiling fin, extension par plugin tiers.

L'API fonctionnelle historique (`clean()`, `normalize_unicode()`, etc.) reste
disponible dans `cleaners.pipeline` et délègue désormais à ce module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from trimtokens.cleaners.pipeline import (
    collapse_whitespace,
    convert_ligatures,
    dedup_paragraphs,
    finalize,
    limit_consecutive_newlines,
    normalize_unicode,
    rejoin_hyphenated,
    strip_invisibles,
    strip_punctuation_only_lines,
)


@runtime_checkable
class CleaningStep(Protocol):
    """Étape de nettoyage atomique. Stateless idéalement (sauf config init)."""

    name: str

    def apply(self, text: str) -> str: ...


@dataclass(frozen=True)
class StepMetrics:
    """Mesure post-exécution d'une étape : entrée/sortie + durée."""

    name: str
    chars_in: int
    chars_out: int
    duration_ms: float

    @property
    def chars_removed(self) -> int:
        return self.chars_in - self.chars_out

    @property
    def reduction_percent(self) -> float:
        if self.chars_in == 0:
            return 0.0
        return round((1 - self.chars_out / self.chars_in) * 100, 2)


# --- Étapes concrètes -----------------------------------------------------
# Wrappers autour des fonctions de `cleaners.pipeline`. Une classe par étape
# pour permettre paramétrage via constructeur + identification stable par `name`.


class NormalizeUnicodeStep:
    name = "normalize_unicode"

    def apply(self, text: str) -> str:
        return normalize_unicode(text)


class StripInvisiblesStep:
    name = "strip_invisibles"

    def apply(self, text: str) -> str:
        return strip_invisibles(text)


class ConvertLigaturesStep:
    name = "convert_ligatures"

    def apply(self, text: str) -> str:
        return convert_ligatures(text)


class RejoinHyphenatedStep:
    name = "rejoin_hyphenated"

    def apply(self, text: str) -> str:
        return rejoin_hyphenated(text)


class CollapseWhitespaceStep:
    name = "collapse_whitespace"

    def apply(self, text: str) -> str:
        return collapse_whitespace(text)


class LimitConsecutiveNewlinesStep:
    name = "limit_consecutive_newlines"

    def __init__(self, max_consecutive: int = 2) -> None:
        self.max_consecutive = max_consecutive

    def apply(self, text: str) -> str:
        return limit_consecutive_newlines(text, max_consecutive=self.max_consecutive)


class DedupParagraphsStep:
    name = "dedup_paragraphs"

    def __init__(self, min_occurrences: int = 3) -> None:
        self.min_occurrences = min_occurrences

    def apply(self, text: str) -> str:
        return dedup_paragraphs(text, min_occurrences=self.min_occurrences)


class StripPunctuationOnlyLinesStep:
    name = "strip_punctuation_only_lines"

    def apply(self, text: str) -> str:
        return strip_punctuation_only_lines(text)


class FinalizeStep:
    name = "finalize"

    def apply(self, text: str) -> str:
        return finalize(text)


# --- Orchestrateur --------------------------------------------------------


@dataclass
class Pipeline:
    """Séquence ordonnée d'étapes de nettoyage.

    Usage :
        pipeline = default_pipeline(aggressive=False)
        text, metrics = pipeline.run(input_text)

    Personnalisation :
        pipeline = Pipeline([NormalizeUnicodeStep(), FinalizeStep()])

    Extension (plugin) : injecter une instance custom qui respecte `CleaningStep`.
    """

    steps: list[CleaningStep] = field(default_factory=list)

    def run(self, text: str) -> tuple[str, list[StepMetrics]]:
        """Exécute les étapes en séquence, retourne (texte_final, métriques_par_étape)."""
        metrics: list[StepMetrics] = []
        for step in self.steps:
            chars_in = len(text)
            t0 = time.perf_counter()
            text = step.apply(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            metrics.append(
                StepMetrics(
                    name=step.name,
                    chars_in=chars_in,
                    chars_out=len(text),
                    duration_ms=round(elapsed_ms, 3),
                )
            )
        return text, metrics

    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]

    def without(self, *names: str) -> Pipeline:
        """Retourne une nouvelle Pipeline avec les étapes nommées désactivées."""
        excluded = set(names)
        return Pipeline(steps=[s for s in self.steps if s.name not in excluded])

    def insert_after(self, target: str, step: CleaningStep) -> Pipeline:
        """Retourne une nouvelle Pipeline avec `step` injectée après l'étape `target`."""
        new_steps: list[CleaningStep] = []
        for s in self.steps:
            new_steps.append(s)
            if s.name == target:
                new_steps.append(step)
        return Pipeline(steps=new_steps)


def aggregate_metrics(metrics: list[StepMetrics]) -> list[StepMetrics]:
    """Agrège plusieurs runs de la même `Pipeline` (typiquement une fois par section).

    Somme chars_in/chars_out/duration_ms par `name`, conserve l'ordre de
    première apparition. Utile pour le rapport global `--profile` côté CLI.

    `StepMetrics` étant `frozen`, on construit des nouvelles instances.
    """
    if not metrics:
        return []

    order: list[str] = []
    acc: dict[str, dict[str, float]] = {}
    for m in metrics:
        if m.name not in acc:
            order.append(m.name)
            acc[m.name] = {"chars_in": 0, "chars_out": 0, "duration_ms": 0.0}
        bucket = acc[m.name]
        bucket["chars_in"] += m.chars_in
        bucket["chars_out"] += m.chars_out
        bucket["duration_ms"] += m.duration_ms

    return [
        StepMetrics(
            name=name,
            chars_in=int(acc[name]["chars_in"]),
            chars_out=int(acc[name]["chars_out"]),
            duration_ms=round(acc[name]["duration_ms"], 3),
        )
        for name in order
    ]


def default_pipeline(*, aggressive: bool = False) -> Pipeline:
    """Pipeline par défaut alignée sur les 11 étapes de la spec (cf TrimTokens.md §4).

    L'étape 7 (suppression headers/footers récurrents) reste page-level et est
    appliquée en amont par `clean()` quand des pages PDF sont fournies — elle ne
    figure pas ici car son signature opère sur `list[str]`, pas `str`.

    `aggressive=True` durcit `dedup_paragraphs` (seuil 2 au lieu de 3).
    """
    return Pipeline(
        steps=[
            NormalizeUnicodeStep(),
            StripInvisiblesStep(),
            ConvertLigaturesStep(),
            RejoinHyphenatedStep(),
            CollapseWhitespaceStep(),
            LimitConsecutiveNewlinesStep(max_consecutive=2),
            DedupParagraphsStep(min_occurrences=2 if aggressive else 3),
            StripPunctuationOnlyLinesStep(),
            LimitConsecutiveNewlinesStep(max_consecutive=2),
            FinalizeStep(),
        ]
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
    "aggregate_metrics",
    "default_pipeline",
]
