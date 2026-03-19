"""
VoiceShield — Attendance Parsing Module
Extracts structured attendance data from voicemail transcripts.
"""

import os
import json
import logging
from typing import Optional
from datetime import date

import httpx
from pydantic import BaseModel

logger = logging.getLogger("voiceshield.attendance")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class AttendanceRecord(BaseModel):
    student_name: str
    reason_type: str  # "absent", "late", "early_pickup"
    reason_detail: str  # "sick with flu", "doctor appointment", etc.
    date: str  # ISO date
    parent_name: Optional[str] = None
    grade: Optional[str] = None
    teacher: Optional[str] = None
    expected_return: Optional[str] = None
    raw_transcript: Optional[str] = None

    def dict(self, **kwargs):
        return super().dict(**kwargs)


ATTENDANCE_PROMPT = """Extract attendance information from this school voicemail transcript.

Return JSON with these fields:
{
    "student_name": "First Last",
    "reason_type": "absent|late|early_pickup",
    "reason_detail": "Description of reason",
    "date": "YYYY-MM-DD",
    "parent_name": "Parent name if mentioned",
    "grade": "Grade/class if mentioned",
    "teacher": "Teacher name if mentioned",
    "expected_return": "Expected return date if mentioned"
}

If you can't extract a field, use null. For date, use today's date if not specified.
Today's date is: {today}

TRANSCRIPT:
"""


async def parse_attendance_record(transcript: str) -> Optional[AttendanceRecord]:
    """Parse an attendance voicemail into structured data."""
    today = date.today().isoformat()

    if ANTHROPIC_API_KEY:
        try:
            return await _parse_with_claude(transcript, today)
        except Exception as e:
            logger.warning(f"Claude attendance parsing failed: {e}")

    if OPENAI_API_KEY:
        try:
            return await _parse_with_openai(transcript, today)
        except Exception as e:
            logger.warning(f"OpenAI attendance parsing failed: {e}")

    return _keyword_parse(transcript, today)


async def _parse_with_claude(transcript: str, today: str) -> AttendanceRecord:
    prompt = ATTENDANCE_PROMPT.format(today=today) + transcript
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
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        return _parse_response(text, transcript)


async def _parse_with_openai(transcript: str, today: str) -> AttendanceRecord:
    prompt = ATTENDANCE_PROMPT.format(today=today) + transcript
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
                    {"role": "system", "content": "Extract attendance data from school voicemails. Respond only in JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return _parse_response(text, transcript)


def _parse_response(text: str, transcript: str) -> AttendanceRecord:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    data = json.loads(text.strip())
    data["raw_transcript"] = transcript
    return AttendanceRecord(**data)


def _keyword_parse(transcript: str, today: str) -> Optional[AttendanceRecord]:
    """Basic keyword extraction as fallback."""
    lower = transcript.lower()

    if "absent" in lower or "not coming" in lower or "sick" in lower:
        reason_type = "absent"
    elif "late" in lower or "tardy" in lower:
        reason_type = "late"
    elif "pick up" in lower or "pickup" in lower:
        reason_type = "early_pickup"
    else:
        return None

    return AttendanceRecord(
        student_name="[needs manual review]",
        reason_type=reason_type,
        reason_detail=transcript[:200],
        date=today,
        raw_transcript=transcript,
    )
