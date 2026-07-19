"""Tests for the council's tolerant status/direction parsers.

The real InferHub brain (ocg/minimax-m3) returns variants like
``"status": "pass"`` (lowercase) and ``"direction": "bullish"`` (not in
the spec enum). The spec-defined parsers used to reject these and mark
every council opinion as ``MISSING`` even though the model produced a
genuine answer. These tests pin the tolerant mapping so the council
stays useful against any of the common model phrasings.
"""

from __future__ import annotations

import pytest

from app.db.models import Direction, ModelStatus
from app.engine.council import _parse_direction, _parse_status


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("VALID", ModelStatus.VALID),
        ("valid", ModelStatus.VALID),
        ("  Valid  ", ModelStatus.VALID),
        ("PASS", ModelStatus.VALID),
        ("OK", ModelStatus.VALID),
        ("YES", ModelStatus.VALID),
        ("CONFIDENT", ModelStatus.VALID),
        ("INVALID", ModelStatus.INVALID),
        ("FAIL", ModelStatus.INVALID),
        ("FAILED", ModelStatus.INVALID),
        ("VETO", ModelStatus.INVALID),
        ("NO", ModelStatus.INVALID),
        ("", ModelStatus.MISSING),
        ("???", ModelStatus.MISSING),
        (None, ModelStatus.MISSING),
    ],
)
def test_parse_status_is_tolerant(raw, expected):
    assert _parse_status(raw) is expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("LONG", Direction.LONG),
        ("long", Direction.LONG),
        ("  Long  ", Direction.LONG),
        ("BUY", Direction.LONG),
        ("BULLISH", Direction.LONG),
        ("BULL", Direction.LONG),
        ("UP", Direction.LONG),
        ("SHORT", Direction.SHORT),
        ("SELL", Direction.SHORT),
        ("BEARISH", Direction.SHORT),
        ("BEAR", Direction.SHORT),
        ("DOWN", Direction.SHORT),
        ("WAIT", Direction.WAIT),
        ("HOLD", Direction.WAIT),
        ("NEUTRAL", Direction.WAIT),
        ("", Direction.WAIT),
        ("???", Direction.WAIT),
        (None, Direction.WAIT),
    ],
)
def test_parse_direction_is_tolerant(raw, expected):
    assert _parse_direction(raw) is expected
