"""Tests for the keyword-based fallback classifier."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from classifier import _keyword_classify, ThreatLevel


def test_critical_threat_detection():
    result = _keyword_classify("I'm going to bring a gun to the school and shoot everyone")
    assert result.threat_level in (ThreatLevel.CRITICAL, ThreatLevel.HIGH)
    assert "gun" in result.threat_keywords or "shoot" in result.threat_keywords
    assert result.category == "threat"


def test_high_threat_detection():
    result = _keyword_classify("I'm going to attack that school and destroy everything")
    assert result.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
    assert result.category == "threat"


def test_attendance_detection():
    result = _keyword_classify("Hi this is Sarah's mom, she won't be in today, she's sick with the flu")
    assert result.is_attendance is True
    assert result.category == "attendance"
    assert result.threat_level == ThreatLevel.NONE


def test_no_threat():
    result = _keyword_classify("Hi, I'm calling to ask about the parent teacher conference schedule next week")
    assert result.threat_level == ThreatLevel.NONE
    assert result.is_attendance is False
    assert result.category == "general_inquiry"


def test_late_arrival():
    result = _keyword_classify("Good morning, this is John's dad. He has a doctor appointment and will be late today, probably arriving around 10 AM")
    assert result.is_attendance is True
    assert result.threat_level == ThreatLevel.NONE


def test_early_pickup():
    result = _keyword_classify("Hi I need to pick up my daughter Emma early today at 1pm for a dental appointment")
    assert result.is_attendance is True
    assert result.threat_level == ThreatLevel.NONE


def test_bomb_threat():
    result = _keyword_classify("There's a bomb in the school. It's going to explode at noon.")
    assert result.threat_level == ThreatLevel.CRITICAL
    assert "bomb" in result.threat_keywords or "explode" in result.threat_keywords
