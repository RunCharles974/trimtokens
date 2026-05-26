"""Tests pour le logging structuré (`logging_setup`)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from trimtokens.logging_setup import (
    ConsoleStructuredFormatter,
    Events,
    JSONFormatter,
    log_event,
    setup_logging,
    teardown_logging,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Garantit un état logging propre avant/après chaque test."""
    teardown_logging()
    yield
    teardown_logging()


def _make_record(
    msg: str,
    *,
    name: str = "trimtokens.test",
    level: int = logging.INFO,
    event_data: dict | None = None,
    exc_info: bool = False,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=(),
        exc_info=None,
    )
    if event_data is not None:
        record.event_data = event_data  # type: ignore[attr-defined]
    if exc_info:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            record.exc_info = sys.exc_info()
    return record


def test_json_formatter_basic_schema() -> None:
    formatter = JSONFormatter()
    record = _make_record("ocr_complete", event_data={"pages": 12, "duration_ms": 4210})

    line = formatter.format(record)
    payload = json.loads(line)

    assert payload["event"] == "ocr_complete"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "trimtokens.test"
    assert payload["data"] == {"pages": 12, "duration_ms": 4210}
    assert "ts" in payload
    # ISO 8601 UTC
    assert payload["ts"].endswith("+00:00")


def test_json_formatter_without_data_omits_data_key() -> None:
    formatter = JSONFormatter()
    record = _make_record("simple_message")
    payload = json.loads(formatter.format(record))
    assert "data" not in payload
    assert payload["event"] == "simple_message"


def test_json_formatter_includes_exception() -> None:
    formatter = JSONFormatter()
    record = _make_record("extraction_failed", exc_info=True)
    payload = json.loads(formatter.format(record))
    assert "exc" in payload
    assert "RuntimeError" in payload["exc"]
    assert "boom" in payload["exc"]


def test_console_formatter_appends_kv_pairs() -> None:
    formatter = ConsoleStructuredFormatter(fmt="%(message)s")
    record = _make_record("ocr_complete", event_data={"pages": 12, "duration_ms": 4210})
    output = formatter.format(record)
    assert "ocr_complete" in output
    assert "pages=12" in output
    assert "duration_ms=4210" in output


def test_console_formatter_no_data_passthrough() -> None:
    formatter = ConsoleStructuredFormatter(fmt="%(message)s")
    record = _make_record("plain message")
    assert formatter.format(record) == "plain message"


def test_log_event_emits_to_json_file(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    setup_logging(level=logging.INFO, console=False, json_file=log_path)

    log = logging.getLogger("trimtokens.test.events")
    log_event(log, Events.OCR_COMPLETE, pages=5, duration_ms=1234, backend="tesseract")
    log_event(log, Events.CACHE_HIT, hits=3)

    teardown_logging()  # flush + close

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["event"] == "ocr_complete"
    assert first["data"]["pages"] == 5
    assert first["data"]["backend"] == "tesseract"

    second = json.loads(lines[1])
    assert second["event"] == "ocr_cache_hit"
    assert second["data"]["hits"] == 3


def test_setup_logging_creates_parent_dir(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "deep" / "events.jsonl"
    setup_logging(level=logging.INFO, console=False, json_file=log_path)
    log = logging.getLogger("trimtokens.test")
    log_event(log, "x", k=1)
    teardown_logging()
    assert log_path.exists()


def test_setup_logging_level_threshold(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    setup_logging(level=logging.WARNING, console=False, json_file=log_path)

    log = logging.getLogger("trimtokens.test")
    log_event(log, "info_event_should_be_filtered", k=1)  # INFO, sous seuil
    log.warning("warning_event")
    log.error("error_event")
    teardown_logging()

    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in content]
    assert "info_event_should_be_filtered" not in events
    assert "warning_event" in events
    assert "error_event" in events


def test_events_catalog_has_stable_strings() -> None:
    """Catalogue d'événements : valeurs snake_case stables (contrat observabilité)."""
    assert Events.OCR_COMPLETE == "ocr_complete"
    assert Events.OCR_START == "ocr_start"
    assert Events.OCR_SKIPPED == "ocr_skipped"
    assert Events.CACHE_HIT == "ocr_cache_hit"
    assert Events.CACHE_MISS == "ocr_cache_miss"
    assert Events.EXTRACTION_START == "extraction_start"
    assert Events.EXTRACTION_COMPLETE == "extraction_complete"
    assert Events.EXTRACTION_FAILED == "extraction_failed"


def test_core_process_emits_extraction_events(tmp_path: Path) -> None:
    """Smoke : `core.process` émet `extraction_start` + `extraction_complete`."""
    log_path = tmp_path / "events.jsonl"
    setup_logging(level=logging.INFO, console=False, json_file=log_path)

    from trimtokens.core import process

    src = tmp_path / "doc.txt"
    src.write_text("hello world", encoding="utf-8")
    process(src)

    teardown_logging()
    events = [json.loads(line)["event"] for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert Events.EXTRACTION_START in events
    assert Events.EXTRACTION_COMPLETE in events


def test_core_process_emits_failure_event(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    setup_logging(level=logging.INFO, console=False, json_file=log_path)

    from trimtokens.core import process
    from trimtokens.exceptions import UnsupportedFormatError

    src = tmp_path / "weird.xyz"
    src.write_text("data", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        process(src)

    teardown_logging()
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    failure_events = [line for line in lines if line["event"] == Events.EXTRACTION_FAILED]
    assert len(failure_events) == 1
    assert failure_events[0]["data"]["error_type"] == "UnsupportedFormatError"
