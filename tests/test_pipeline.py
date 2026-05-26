"""Tests du pipeline de nettoyage (Phase 1) — couvre les 11 étapes."""

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


def test_step1_nfkc_normalizes_compatibility_forms() -> None:
    # caractère "ﬁ" (U+FB01) est traité par NFKC en "fi"
    # mais on isole ici : NFKC convertit aussi "①" → "1", "K" (Kelvin U+212A) → "K"
    result = normalize_unicode("K")  # U+212A Kelvin sign
    assert result == "K"  # K latin majuscule


def test_step2_strips_zero_width_and_bom() -> None:
    text = "hello​‌‍﻿world"
    assert strip_invisibles(text) == "helloworld"


def test_step2_strips_soft_hyphen() -> None:
    assert strip_invisibles("café­au­lait") == "caféaulait"


def test_step2_strips_control_chars_but_keeps_tabs_and_newlines() -> None:
    text = "line1\n\tindented\x00\x07\rline2"
    out = strip_invisibles(text)
    assert "\x00" not in out
    assert "\x07" not in out
    assert "\n" in out
    assert "\t" in out


def test_step3_converts_ligatures() -> None:
    text = "ﬁnale ﬂag aﬀaire eﬃcace souﬄer"
    assert convert_ligatures(text) == "finale flag affaire efficace souffler"


def test_step3_converts_each_ligature_individually() -> None:
    assert convert_ligatures("ﬁ") == "fi"
    assert convert_ligatures("ﬂ") == "fl"
    assert convert_ligatures("ﬀ") == "ff"
    assert convert_ligatures("ﬃ") == "ffi"
    assert convert_ligatures("ﬄ") == "ffl"


def test_step4_rejoins_hyphenated_words() -> None:
    text = "Ceci est un exem-\nple de mot coupé."
    assert rejoin_hyphenated(text) == "Ceci est un exemple de mot coupé."


def test_step4_does_not_join_normal_hyphens() -> None:
    text = "porte-monnaie"
    assert rejoin_hyphenated(text) == "porte-monnaie"


def test_step5_collapses_multiple_spaces_and_tabs() -> None:
    text = "hello    world\t\tfoo"
    assert collapse_whitespace(text) == "hello world foo"


def test_step5_preserves_newlines() -> None:
    text = "line1   \n  line2"
    out = collapse_whitespace(text)
    assert out == "line1\nline2"


def test_step6_limits_consecutive_newlines() -> None:
    text = "a\n\n\n\n\nb"
    assert limit_consecutive_newlines(text, max_consecutive=2) == "a\n\nb"


def test_step6_keeps_double_newlines() -> None:
    text = "a\n\nb"
    assert limit_consecutive_newlines(text, max_consecutive=2) == "a\n\nb"


def test_step7_strips_recurring_headers_footers() -> None:
    pages = [
        "ACME Corp - Confidentiel\nContenu unique page 1\nPage 1 / 4",
        "ACME Corp - Confidentiel\nContenu unique page 2\nPage 2 / 4",
        "ACME Corp - Confidentiel\nContenu unique page 3\nPage 3 / 4",
        "ACME Corp - Confidentiel\nContenu unique page 4\nPage 4 / 4",
    ]
    cleaned = strip_recurring_headers_footers(pages)
    joined = "\n".join(cleaned)
    assert "ACME Corp - Confidentiel" not in joined
    assert "Page 1 / 4" not in joined
    assert "Contenu unique page 1" in joined
    assert "Contenu unique page 4" in joined


def test_step7_keeps_unique_lines() -> None:
    pages = ["unique A", "unique B", "unique C"]
    cleaned = strip_recurring_headers_footers(pages)
    assert cleaned == pages


def test_step7_strips_page_numbers_even_below_threshold() -> None:
    pages = ["contenu A\nPage 1", "contenu B\nPage 2"]
    cleaned = strip_recurring_headers_footers(pages)
    assert "Page 1" not in "\n".join(cleaned)
    assert "Page 2" not in "\n".join(cleaned)


def test_step8_deduplicates_paragraphs() -> None:
    text = "para A\n\npara B\n\npara A\n\npara C\n\npara A"
    out = dedup_paragraphs(text, min_occurrences=3)
    occurrences = out.count("para A")
    assert occurrences == 1
    assert "para B" in out
    assert "para C" in out


def test_step8_keeps_paragraph_appearing_twice() -> None:
    text = "para A\n\npara B\n\npara A"
    out = dedup_paragraphs(text, min_occurrences=3)
    assert out.count("para A") == 2


def test_step9_strips_punctuation_only_lines() -> None:
    text = "Real content\n---\n***\n???\nMore content"
    out = strip_punctuation_only_lines(text)
    assert "Real content" in out
    assert "More content" in out
    assert "---" not in out
    assert "***" not in out
    assert "???" not in out


def test_step9_keeps_lines_with_mixed_content() -> None:
    text = "Q: what is 2+2?\nA: 4."
    out = strip_punctuation_only_lines(text)
    assert "Q: what is 2+2?" in out
    assert "A: 4." in out


def test_step10_normalizes_crlf_and_trims() -> None:
    text = "\r\n\r\nhello\r\nworld\r\n\r\n"
    assert finalize(text) == "hello\nworld"


def test_full_pipeline_text_mode_reduces_chars() -> None:
    raw = "hello​world\n\n\n\n\nfoo   bar\n\n---\n\nfoo   bar\n\n---\n\nfoo   bar"
    cleaned, stats = clean(text=raw)
    assert stats.cleaned_chars < stats.original_chars
    assert "​" not in cleaned
    assert "---" not in cleaned


def test_full_pipeline_paged_mode_strips_headers() -> None:
    pages = [
        "Confidentiel ACME\n\nContenu réel page 1.\n\nPage 1",
        "Confidentiel ACME\n\nContenu réel page 2.\n\nPage 2",
        "Confidentiel ACME\n\nContenu réel page 3.\n\nPage 3",
    ]
    cleaned, stats = clean(pages=pages)
    assert "Confidentiel ACME" not in cleaned
    assert "Page 1" not in cleaned
    assert "Contenu réel page 1." in cleaned
    assert stats.cleaned_chars > 0


def test_full_pipeline_aggressive_dedups_at_2_occurrences() -> None:
    raw = "para X\n\npara Y\n\npara X"
    cleaned, _ = clean(text=raw, aggressive=True)
    assert cleaned.count("para X") == 1


def test_full_pipeline_returns_stats_with_byte_counts() -> None:
    raw = "hello world"
    cleaned, stats = clean(text=raw, original_size_bytes=1024)
    assert stats.original_size_bytes == 1024
    assert stats.cleaned_size_bytes == len(cleaned.encode("utf-8"))
    assert stats.tokens_estimated > 0
    assert stats.tokens_original_estimated > 0


def test_full_pipeline_idempotent_on_already_clean_text() -> None:
    clean_input = "Ligne 1.\n\nLigne 2."
    once, _ = clean(text=clean_input)
    twice, _ = clean(text=once)
    assert once == twice


def test_full_pipeline_handles_ligature_in_real_text() -> None:
    raw = "Le coeﬃcient n'est pas suﬃsant."
    cleaned, _ = clean(text=raw)
    assert "ﬃ" not in cleaned
    assert cleaned == "Le coefficient n'est pas suffisant."


def test_full_pipeline_rejects_both_text_and_pages() -> None:
    import pytest

    with pytest.raises(ValueError):
        clean(text="a", pages=["b"])


def test_full_pipeline_rejects_neither_text_nor_pages() -> None:
    import pytest

    with pytest.raises(ValueError):
        clean()
