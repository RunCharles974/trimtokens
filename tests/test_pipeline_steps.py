"""Tests pour le pipeline orienté étapes (`cleaners.steps`)."""

from __future__ import annotations

import pytest

from trimtokens.cleaners import (
    CleaningStep,
    DedupParagraphsStep,
    FinalizeStep,
    LimitConsecutiveNewlinesStep,
    NormalizeUnicodeStep,
    Pipeline,
    StepMetrics,
    clean,
    default_pipeline,
)


def test_default_pipeline_step_names_in_order() -> None:
    pipe = default_pipeline()
    assert pipe.step_names() == [
        "normalize_unicode",
        "strip_invisibles",
        "convert_ligatures",
        "rejoin_hyphenated",
        "collapse_whitespace",
        "limit_consecutive_newlines",
        "dedup_paragraphs",
        "strip_punctuation_only_lines",
        "limit_consecutive_newlines",
        "finalize",
    ]


def test_default_pipeline_aggressive_lowers_dedup_threshold() -> None:
    pipe = default_pipeline(aggressive=True)
    dedup = next(s for s in pipe.steps if s.name == "dedup_paragraphs")
    assert isinstance(dedup, DedupParagraphsStep)
    assert dedup.min_occurrences == 2

    pipe_default = default_pipeline()
    dedup_default = next(s for s in pipe_default.steps if s.name == "dedup_paragraphs")
    assert isinstance(dedup_default, DedupParagraphsStep)
    assert dedup_default.min_occurrences == 3


def test_pipeline_run_returns_text_and_metrics() -> None:
    pipe = default_pipeline()
    text, metrics = pipe.run("Hello​   world\n\n\n\n\nfoo")
    assert "Hello world" in text
    assert "\n\n\n" not in text
    assert len(metrics) == len(pipe.steps)
    assert all(isinstance(m, StepMetrics) for m in metrics)


def test_step_metrics_fields() -> None:
    pipe = Pipeline(steps=[NormalizeUnicodeStep(), FinalizeStep()])
    text, metrics = pipe.run("  abc  ")
    assert text == "abc"
    finalize_metric = metrics[-1]
    assert finalize_metric.name == "finalize"
    assert finalize_metric.chars_in >= finalize_metric.chars_out
    assert finalize_metric.chars_removed >= 0
    assert finalize_metric.duration_ms >= 0
    assert 0.0 <= finalize_metric.reduction_percent <= 100.0


def test_pipeline_without_excludes_named_steps() -> None:
    pipe = default_pipeline()
    pruned = pipe.without("dedup_paragraphs", "convert_ligatures")
    names = pruned.step_names()
    assert "dedup_paragraphs" not in names
    assert "convert_ligatures" not in names
    # autres étapes préservées
    assert "normalize_unicode" in names
    assert "finalize" in names


def test_pipeline_insert_after_injects_custom_step() -> None:
    class UpperStep:
        name = "upper"

        def apply(self, text: str) -> str:
            return text.upper()

    pipe = Pipeline(steps=[NormalizeUnicodeStep(), FinalizeStep()])
    extended = pipe.insert_after("normalize_unicode", UpperStep())

    assert extended.step_names() == ["normalize_unicode", "upper", "finalize"]

    text, _ = extended.run("hello")
    assert text == "HELLO"


def test_custom_pipeline_respects_protocol() -> None:
    class NoopStep:
        name = "noop"

        def apply(self, text: str) -> str:
            return text

    step: CleaningStep = NoopStep()
    pipe = Pipeline(steps=[step])
    text, metrics = pipe.run("unchanged")
    assert text == "unchanged"
    assert metrics[0].name == "noop"


def test_clean_uses_default_pipeline_when_none() -> None:
    out, stats = clean(text="Hello​ world\n\n\n\nfoo")
    assert "Hello world" in out
    assert stats.cleaned_chars <= stats.original_chars


def test_clean_accepts_custom_pipeline() -> None:
    custom = Pipeline(
        steps=[
            NormalizeUnicodeStep(),
            LimitConsecutiveNewlinesStep(max_consecutive=1),
            FinalizeStep(),
        ]
    )
    out, _ = clean(text="a\n\n\n\nb", pipeline=custom)
    assert out == "a\nb"


def test_clean_custom_pipeline_skips_dedup() -> None:
    """Pipeline sans dedup → paragraphes répétés préservés."""
    raw = "ABC\n\nABC\n\nABC\n\nABC"
    minimal = Pipeline(steps=[NormalizeUnicodeStep(), FinalizeStep()])
    out_no_dedup, _ = clean(text=raw, pipeline=minimal)
    assert out_no_dedup.count("ABC") == 4

    out_default, _ = clean(text=raw)
    assert out_default.count("ABC") == 1


def test_clean_rejects_both_text_and_pages() -> None:
    with pytest.raises(ValueError, match="pas les deux"):
        clean(text="x", pages=["a", "b"])


def test_clean_rejects_neither_text_nor_pages() -> None:
    with pytest.raises(ValueError, match="Fournir"):
        clean()
