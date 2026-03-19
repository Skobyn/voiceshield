"""
VoiceShield — Voicemail Classifier
Uses Claude/OpenAI to classify voicemails for threats and attendance.
"""

import os
import json
import logging
from enum import Enum
from typing import List, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger("voiceshield.classifier")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VoicemailClassification(BaseModel):
    threat_level: ThreatLevel
    threat_keywords: List[str] = []
    category: str  # "threat", "attendance", "general_inquiry", "spam", "wrong_number", etc.
    is_attendance: bool = False
    confidence: float = 0.0
    reasoning: str = ""

    def dict(self, **kwargs):
        d = super().dict(**kwargs)
        d["threat_level"] = self.threat_level.value
        return d


CLASSIFICATION_PROMPT = """You are a school voicemail security classifier. Analyze the following voicemail transcript and classify it.

CRITICAL: Schools rely on this for safety. Be sensitive to threats but avoid false positives on normal parent communication.

Classify into one of these categories:
- "threat" — Contains language about weapons, violence, harm to students/staff, bombs, shooting, attack
- "attendance" — Parent/guardian reporting a student absence, late arrival, or early pickup
- "general_inquiry" — Normal school business (questions about events, schedules, enrollment)
- "spam" — Telemarketing, robocalls, irrelevant
- "wrong_number" — Caller reached the wrong number
- "other" — Anything else

Threat levels:
- "none" — No threat language at all
- "low" — Vaguely concerning but likely benign (e.g., frustrated parent venting)
- "medium" — Ambiguous language that could be threatening; needs human review
- "high" — Clear threatening language directed at the school, students, or staff
- "critical" — Imminent, specific threat (named target, time, weapon type)

Respond in JSON only:
{
    "threat_level": "none|low|medium|high|critical",
    "threat_keywords": ["list", "of", "flagged", "words"],
    "category": "threat|attendance|general_inquiry|spam|wrong_number|other",
    "is_attendance": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}

TRANSCRIPT:
"""


async def classify_voicemail(transcript: str) -> VoicemailClassification:
    """Classify a voicemail transcript for threats and category."""
    if ANTHROPIC_API_KEY:
        try:
            return await _classify_with_claude(transcript)
        except Exception as e:
            logger.warning(f"Claude classification failed: {e}")

    if OPENAI_API_KEY:
        return await _classify_with_openai(transcript)

    # Fallback: keyword-based classification
    return _keyword_classify(transcript)


async def _classify_with_claude(transcript: str) -> VoicemailClassification:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": CLASSIFICATION_PROMPT + transcript}
                ],
            },
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        # Extract JSON from response
        return _parse_classification(text)


async def _classify_with_openai(transcript: str) -> VoicemailClassification:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a school voicemail security classifier. Respond only in JSON."},
                    {"role": "user", "content": CLASSIFICATION_PROMPT + transcript},
                ],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return _parse_classification(text)


def _parse_classification(text: str) -> VoicemailClassification:
    """Parse LLM JSON response into classification."""
    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    data = json.loads(text.strip())
    return VoicemailClassification(**data)


# ──────────────────────────────────────────────
# Keyword Fallback (no LLM)
# ──────────────────────────────────────────────

THREAT_KEYWORDS = {
    "critical": ["bomb", "shoot", "gun", "kill", "murder", "explode", "detonate", "weapon", "rifle", "pistol"],
    "high": ["hurt", "attack", "destroy", "threat", "die", "death", "stab", "knife", "fire"],
    "medium": ["angry", "revenge", "pay for this", "regret", "sorry", "consequences"],
}

ATTENDANCE_KEYWORDS = ["absent", "absence", "sick", "not coming", "won't be in", "staying home",
                        "doctor", "appointment", "late", "tardy", "early pickup", "pick up early",
                        "not feeling well", "fever", "flu", "cold"]


def _keyword_classify(transcript: str) -> VoicemailClassification:
    """Basic keyword-based classification as fallback."""
    lower = transcript.lower()
    found_keywords = []
    threat_level = ThreatLevel.NONE

    for level_name, keywords in THREAT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                found_keywords.append(kw)
                if ThreatLevel(level_name).value > threat_level.value or threat_level == ThreatLevel.NONE:
                    threat_level = ThreatLevel(level_name)

    is_attendance = any(kw in lower for kw in ATTENDANCE_KEYWORDS)
    category = "attendance" if is_attendance else ("threat" if found_keywords else "general_inquiry")

    return VoicemailClassification(
        threat_level=threat_level,
        threat_keywords=found_keywords,
        category=category,
        is_attendance=is_attendance,
        confidence=0.5,  # Lower confidence for keyword-only
        reasoning="Keyword-based classification (no LLM API key configured)",
    )
