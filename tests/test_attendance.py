"""Tests for keyword-based attendance parsing fallback."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from attendance import _keyword_parse
from datetime import date


def test_absent_detection():
    result = _keyword_parse("My son Jake won't be coming in today, he's sick", date.today().isoformat())
    assert result is not None
    assert result.reason_type == "absent"


def test_late_detection():
    result = _keyword_parse("Tommy will be late today, he has a morning appointment", date.today().isoformat())
    assert result is not None
    assert result.reason_type == "late"


def test_pickup_detection():
    result = _keyword_parse("I need to pick up my daughter at 2pm today", date.today().isoformat())
    assert result is not None
    assert result.reason_type == "early_pickup"


def test_non_attendance():
    result = _keyword_parse("What time does the school play start on Friday?", date.today().isoformat())
    assert result is None
