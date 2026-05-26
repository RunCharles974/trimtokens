"""Tests du module stats (tokens + compute_stats)."""

from __future__ import annotations

from trimtokens.stats import compute_stats, estimate_tokens


def test_estimate_tokens_empty_string() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_returns_positive_count() -> None:
    assert estimate_tokens("hello world") > 0


def test_estimate_tokens_scales_with_text_size() -> None:
    short = estimate_tokens("hello")
    long = estimate_tokens("hello " * 100)
    assert long > short


def test_compute_stats_byte_count_matches_utf8() -> None:
    cleaned = "café"
    stats = compute_stats(
        original_size_bytes=100,
        original_chars=10,
        cleaned_text=cleaned,
    )
    assert stats.cleaned_size_bytes == len(cleaned.encode("utf-8"))
    assert stats.cleaned_chars == 4
    assert stats.original_size_bytes == 100
    assert stats.original_chars == 10


def test_compute_stats_reduction_percent() -> None:
    stats = compute_stats(
        original_size_bytes=1000,
        original_chars=500,
        cleaned_text="x" * 100,
    )
    assert stats.cleaned_size_bytes == 100
    assert stats.reduction_percent == 90.0


def test_compute_stats_zero_original_returns_zero_reduction() -> None:
    stats = compute_stats(
        original_size_bytes=0,
        original_chars=0,
        cleaned_text="",
    )
    assert stats.reduction_percent == 0.0
    assert stats.tokens_reduction_percent == 0.0


def test_compute_stats_with_original_text_uses_real_token_count() -> None:
    original = "ceci est un texte beaucoup plus long que la version nettoyée"
    cleaned = "texte court"
    stats = compute_stats(
        original_size_bytes=len(original.encode("utf-8")),
        original_chars=len(original),
        cleaned_text=cleaned,
        original_text=original,
    )
    assert stats.tokens_original_estimated > stats.tokens_estimated
    assert stats.tokens_reduction_percent > 0
