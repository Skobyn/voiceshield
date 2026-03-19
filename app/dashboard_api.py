"""
VoiceShield — Dashboard API Endpoints
Serves data for the web dashboard UI.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from storage import (
    get_voicemail_records,
    get_attendance_records,
    get_school_config,
    _voicemail_records,
    _attendance_records,
    _school_configs,
)

logger = logging.getLogger("voiceshield.dashboard")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ──────────────────────────────────────────────
# Mock Data Seeder
# ──────────────────────────────────────────────

MOCK_DATA_SEEDED = False


def seed_mock_data():
    """Seed realistic mock data for the demo dashboard."""
    global MOCK_DATA_SEEDED
    if MOCK_DATA_SEEDED:
        return
    MOCK_DATA_SEEDED = True

    now = datetime.now(timezone.utc)

    # Add some school configs
    _school_configs.update({
        "lincoln-elementary": {
            "school_name": "Lincoln Elementary",
            "admin_phones": ["+15551001001"],
            "admin_emails": ["admin@lincoln-elementary.edu", "principal@lincoln-elementary.edu"],
            "police_phone": "+15559110001",
            "police_email": "dispatch@springfield-pd.gov",
            "webhook_url": "https://hooks.slack.com/services/XXXXX",
            "attendance_webhook_url": "https://sis.lincoln-elementary.edu/api/attendance",
            "attendance_line": "+15551001099",
            "alert_keywords": ["gun", "bomb", "shoot", "kill", "weapon", "knife", "attack", "hurt", "fire"],
            "sensitivity": "high",
        },
        "washington-middle": {
            "school_name": "Washington Middle School",
            "admin_phones": ["+15552002001", "+15552002002"],
            "admin_emails": ["office@washington-middle.edu"],
            "police_phone": "+15559110002",
            "police_email": "dispatch@springfield-pd.gov",
            "webhook_url": None,
            "attendance_webhook_url": None,
            "attendance_line": "+15552002099",
            "alert_keywords": ["gun", "bomb", "shoot", "kill", "weapon"],
            "sensitivity": "medium",
        },
        "jefferson-high": {
            "school_name": "Jefferson High School",
            "admin_phones": ["+15553003001"],
            "admin_emails": ["security@jefferson-high.edu", "principal@jefferson-high.edu"],
            "police_phone": "+15559110003",
            "police_email": "dispatch@springfield-pd.gov",
            "webhook_url": "https://hooks.slack.com/services/YYYYY",
            "attendance_webhook_url": "https://powerschool.jefferson-high.edu/webhook",
            "attendance_line": "+15553003099",
            "alert_keywords": ["gun", "bomb", "shoot", "kill", "weapon", "knife", "attack", "hurt", "fire", "threat"],
            "sensitivity": "high",
        },
    })

    # Voicemail records spanning the last 7 days
    mock_voicemails = [
        # Today — early morning threat (4:30 AM)
        {"recording_sid": "REC-000", "caller": "BLOCKED", "called_number": "+15551001001", "school_id": "lincoln-elementary",
         "transcript": "Listen to me very carefully. I have a gun and I'm bringing it to Lincoln Elementary this morning. By the time the kids get there, it's going to be too late. You people ruined my family and now you're going to pay for it.",
         "threat_level": "critical", "threat_keywords": ["gun", "bringing it", "too late", "pay for it"], "category": "threat", "is_attendance": False,
         "confidence": 0.99, "timestamp": now.replace(hour=4, minute=30, second=0, microsecond=0).isoformat(), "processing_time_ms": 1180,
         "alert_sent": True, "alert_targets": ["admin@lincoln-elementary.edu", "principal@lincoln-elementary.edu", "dispatch@springfield-pd.gov", "+15559110001"]},

        # Today
        {"recording_sid": "REC-001", "caller": "+15551234567", "called_number": "+15551001099", "school_id": "lincoln-elementary",
         "transcript": "Hi, this is Maria Garcia calling about my son Diego. He has a fever and won't be coming to school today. He's in Mrs. Patterson's third grade class. Thank you.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.97, "timestamp": (now - timedelta(hours=1)).isoformat(), "processing_time_ms": 2340,
         "attendance_record": {"student_name": "Diego Garcia", "reason": "sick - fever", "date": now.strftime("%Y-%m-%d"), "type": "absent", "guardian": "Maria Garcia"}},

        {"recording_sid": "REC-002", "caller": "+15559876543", "called_number": "+15551001099", "school_id": "lincoln-elementary",
         "transcript": "Good morning, this is James Wilson. My daughter Emma will be late today, she has a dentist appointment at 9 and should be there by 10:30. She's in fifth grade, room 12.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.96, "timestamp": (now - timedelta(hours=2)).isoformat(), "processing_time_ms": 1890,
         "attendance_record": {"student_name": "Emma Wilson", "reason": "dentist appointment", "date": now.strftime("%Y-%m-%d"), "type": "late", "guardian": "James Wilson"}},

        {"recording_sid": "REC-003", "caller": "+15557778888", "called_number": "+15552002099", "school_id": "washington-middle",
         "transcript": "Hello, I need to pick up my son Tyler Brooks early today at 2pm. He has an orthodontist appointment. He's in 7th grade. My name is Sarah Brooks, I'm listed as his emergency contact.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.95, "timestamp": (now - timedelta(hours=3)).isoformat(), "processing_time_ms": 2100,
         "attendance_record": {"student_name": "Tyler Brooks", "reason": "orthodontist appointment", "date": now.strftime("%Y-%m-%d"), "type": "early_pickup", "guardian": "Sarah Brooks"}},

        {"recording_sid": "REC-004", "caller": "BLOCKED", "called_number": "+15553003001", "school_id": "jefferson-high",
         "transcript": "You people at Jefferson are going to pay for what you did to my kid. I'm coming up there and someone is going to get hurt. You better watch yourselves.",
         "threat_level": "high", "threat_keywords": ["pay", "hurt"], "category": "threat", "is_attendance": False,
         "confidence": 0.92, "timestamp": (now - timedelta(hours=4)).isoformat(), "processing_time_ms": 1560,
         "alert_sent": True, "alert_targets": ["security@jefferson-high.edu", "dispatch@springfield-pd.gov"]},

        {"recording_sid": "REC-005", "caller": "+15554443333", "called_number": "+15551001001", "school_id": "lincoln-elementary",
         "transcript": "Hi, I'm calling to ask about the spring concert schedule. When is the 4th grade performance? Also, do parents need tickets or is it open seating? Thank you!",
         "threat_level": "none", "threat_keywords": [], "category": "general_inquiry", "is_attendance": False,
         "confidence": 0.98, "timestamp": (now - timedelta(hours=5)).isoformat(), "processing_time_ms": 1750},

        # Yesterday
        {"recording_sid": "REC-006", "caller": "+15552223333", "called_number": "+15551001099", "school_id": "lincoln-elementary",
         "transcript": "This is Tom Chen, calling about my daughter Lily Chen. She was throwing up this morning and won't be at school today or probably tomorrow. She's in second grade with Mr. Adams.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.97, "timestamp": (now - timedelta(days=1, hours=2)).isoformat(), "processing_time_ms": 2200,
         "attendance_record": {"student_name": "Lily Chen", "reason": "sick - vomiting", "date": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "type": "absent", "guardian": "Tom Chen"}},

        {"recording_sid": "REC-007", "caller": "+15558887777", "called_number": "+15553003099", "school_id": "jefferson-high",
         "transcript": "Hey, this is Mike Johnson. My son Ryan won't be in school today, he's got a cold. He's a sophomore. Thanks.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.96, "timestamp": (now - timedelta(days=1, hours=3)).isoformat(), "processing_time_ms": 1680,
         "attendance_record": {"student_name": "Ryan Johnson", "reason": "cold", "date": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "type": "absent", "guardian": "Mike Johnson"}},

        {"recording_sid": "REC-008", "caller": "+15556665555", "called_number": "+15552002001", "school_id": "washington-middle",
         "transcript": "I am extremely frustrated with this school. My child keeps getting bullied and nobody does anything about it. If this doesn't stop I'm going to have to take matters into my own hands and go to the school board.",
         "threat_level": "medium", "threat_keywords": ["take matters into my own hands"], "category": "general_inquiry", "is_attendance": False,
         "confidence": 0.78, "timestamp": (now - timedelta(days=1, hours=5)).isoformat(), "processing_time_ms": 2450,
         "alert_sent": False, "needs_review": True},

        # 2 days ago
        {"recording_sid": "REC-009", "caller": "+15551112222", "called_number": "+15551001099", "school_id": "lincoln-elementary",
         "transcript": "Good morning, this is Rachel Kim. My twins Sophia and Ethan Kim will not be in school today. We have a family emergency and need to travel out of state. They should be back by Thursday. They're in first grade.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.95, "timestamp": (now - timedelta(days=2, hours=1)).isoformat(), "processing_time_ms": 2100,
         "attendance_record": {"student_name": "Sophia Kim, Ethan Kim", "reason": "family emergency", "date": (now - timedelta(days=2)).strftime("%Y-%m-%d"), "type": "absent", "guardian": "Rachel Kim"}},

        {"recording_sid": "REC-010", "caller": "+15559990000", "called_number": "+15553003001", "school_id": "jefferson-high",
         "transcript": "Yeah hi this is about your extended car warranty. We've been trying to reach you about...",
         "threat_level": "none", "threat_keywords": [], "category": "spam", "is_attendance": False,
         "confidence": 0.99, "timestamp": (now - timedelta(days=2, hours=4)).isoformat(), "processing_time_ms": 980},

        # 3 days ago
        {"recording_sid": "REC-011", "caller": "RESTRICTED", "called_number": "+15553003001", "school_id": "jefferson-high",
         "transcript": "There's going to be a shooting at Jefferson High on Friday. I'm not kidding. People are going to die.",
         "threat_level": "critical", "threat_keywords": ["shooting", "die"], "category": "threat", "is_attendance": False,
         "confidence": 0.99, "timestamp": (now - timedelta(days=3, hours=6)).isoformat(), "processing_time_ms": 1200,
         "alert_sent": True, "alert_targets": ["security@jefferson-high.edu", "principal@jefferson-high.edu", "dispatch@springfield-pd.gov", "+15559110003"]},

        {"recording_sid": "REC-012", "caller": "+15553334444", "called_number": "+15552002099", "school_id": "washington-middle",
         "transcript": "Hi, I'm Andrea Lopez. My daughter Mia Lopez in 8th grade will be absent today. She has a stomach bug. Thank you.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.97, "timestamp": (now - timedelta(days=3, hours=2)).isoformat(), "processing_time_ms": 1950,
         "attendance_record": {"student_name": "Mia Lopez", "reason": "stomach bug", "date": (now - timedelta(days=3)).strftime("%Y-%m-%d"), "type": "absent", "guardian": "Andrea Lopez"}},

        # 4-6 days ago
        {"recording_sid": "REC-013", "caller": "+15557776666", "called_number": "+15551001099", "school_id": "lincoln-elementary",
         "transcript": "This is Pat O'Brien. Calling to let you know Connor will be late today, our car broke down. He should be there by 9:30. He's in 4th grade.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.96, "timestamp": (now - timedelta(days=4, hours=1)).isoformat(), "processing_time_ms": 1800,
         "attendance_record": {"student_name": "Connor O'Brien", "reason": "car broke down", "date": (now - timedelta(days=4)).strftime("%Y-%m-%d"), "type": "late", "guardian": "Pat O'Brien"}},

        {"recording_sid": "REC-014", "caller": "+15554445555", "called_number": "+15552002001", "school_id": "washington-middle",
         "transcript": "Hello, I wanted to inquire about the registration process for next year. My family is moving to the district and I'd like to enroll my child. Can someone call me back?",
         "threat_level": "none", "threat_keywords": [], "category": "general_inquiry", "is_attendance": False,
         "confidence": 0.98, "timestamp": (now - timedelta(days=5, hours=3)).isoformat(), "processing_time_ms": 1650},

        {"recording_sid": "REC-015", "caller": "+15558889999", "called_number": "+15553003099", "school_id": "jefferson-high",
         "transcript": "Hey this is Dave Martinez, my son Alex is sick, won't be in today. He's a junior.",
         "threat_level": "none", "threat_keywords": [], "category": "attendance", "is_attendance": True,
         "confidence": 0.95, "timestamp": (now - timedelta(days=5, hours=2)).isoformat(), "processing_time_ms": 1550,
         "attendance_record": {"student_name": "Alex Martinez", "reason": "sick", "date": (now - timedelta(days=5)).strftime("%Y-%m-%d"), "type": "absent", "guardian": "Dave Martinez"}},

        {"recording_sid": "REC-016", "caller": "+15551239876", "called_number": "+15551001001", "school_id": "lincoln-elementary",
         "transcript": "Um, hello? I think I have the wrong number. I was trying to reach Dr. Mitchell's office? Sorry about that.",
         "threat_level": "none", "threat_keywords": [], "category": "wrong_number", "is_attendance": False,
         "confidence": 0.99, "timestamp": (now - timedelta(days=6, hours=4)).isoformat(), "processing_time_ms": 1100},

        {"recording_sid": "REC-017", "caller": "+15556667777", "called_number": "+15553003001", "school_id": "jefferson-high",
         "transcript": "I'm going to burn that school to the ground if my kid gets suspended one more time. This is ridiculous.",
         "threat_level": "high", "threat_keywords": ["burn", "ground"], "category": "threat", "is_attendance": False,
         "confidence": 0.88, "timestamp": (now - timedelta(days=6, hours=5)).isoformat(), "processing_time_ms": 1700,
         "alert_sent": True, "alert_targets": ["security@jefferson-high.edu", "dispatch@springfield-pd.gov"]},
    ]

    _voicemail_records.extend(mock_voicemails)

    # Seed attendance records from voicemails
    for vm in mock_voicemails:
        if vm.get("attendance_record"):
            rec = vm["attendance_record"].copy()
            rec["school_id"] = vm["school_id"]
            rec["recording_sid"] = vm["recording_sid"]
            rec["timestamp"] = vm["timestamp"]
            _attendance_records.append(rec)


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@router.get("/schools")
async def list_schools():
    """List all configured schools."""
    seed_mock_data()
    schools = []
    for sid, config in _school_configs.items():
        if sid in ("default", "demo-school"):
            continue
        schools.append({"id": sid, "name": config.get("school_name", sid), **config})
    return {"schools": schools}


@router.get("/voicemails")
async def list_voicemails(
    school_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    threat_level: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List voicemail records with optional filters."""
    seed_mock_data()
    records = _voicemail_records[:]
    if school_id:
        records = [r for r in records if r.get("school_id") == school_id]
    if category:
        records = [r for r in records if r.get("category") == category]
    if threat_level:
        records = [r for r in records if r.get("threat_level") == threat_level]
    return {"voicemails": records[:limit], "total": len(records)}


@router.get("/threats")
async def list_threats(school_id: Optional[str] = Query(None)):
    """List only threat-classified voicemails."""
    seed_mock_data()
    records = _voicemail_records[:]
    if school_id:
        records = [r for r in records if r.get("school_id") == school_id]
    threats = [r for r in records if r.get("threat_level") not in ("none", None)]
    threats.sort(key=lambda r: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.get("threat_level", "low"), 4))
    return {"threats": threats, "total": len(threats)}


@router.get("/attendance")
async def list_attendance(school_id: Optional[str] = Query(None)):
    """List attendance records."""
    seed_mock_data()
    records = _attendance_records[:]
    if school_id:
        records = [r for r in records if r.get("school_id") == school_id]
    return {"records": records, "total": len(records)}


@router.get("/stats")
async def get_stats(school_id: Optional[str] = Query(None)):
    """Compute dashboard statistics."""
    seed_mock_data()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    records = _voicemail_records[:]
    if school_id:
        records = [r for r in records if r.get("school_id") == school_id]

    def parse_ts(r):
        ts = r.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except:
            return now - timedelta(days=30)

    today_records = [r for r in records if parse_ts(r) >= today_start]
    week_records = [r for r in records if parse_ts(r) >= week_start]

    # Threat breakdown
    threat_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in records:
        tl = r.get("threat_level", "none")
        if tl in threat_breakdown:
            threat_breakdown[tl] += 1

    # Attendance breakdown
    att_records = _attendance_records[:]
    if school_id:
        att_records = [r for r in att_records if r.get("school_id") == school_id]
    att_breakdown = {"absent": 0, "late": 0, "early_pickup": 0}
    for r in att_records:
        t = r.get("type", "absent")
        if t in att_breakdown:
            att_breakdown[t] += 1

    # Category breakdown
    cat_breakdown = {}
    for r in records:
        cat = r.get("category", "other")
        cat_breakdown[cat] = cat_breakdown.get(cat, 0) + 1

    # Daily volume (last 7 days)
    daily_volume = {}
    for i in range(7):
        day = (today_start - timedelta(days=i))
        day_str = day.strftime("%Y-%m-%d")
        day_end = day + timedelta(days=1)
        count = len([r for r in records if day <= parse_ts(r) < day_end])
        daily_volume[day_str] = count

    # Average processing time
    proc_times = [r.get("processing_time_ms", 0) for r in records if r.get("processing_time_ms")]
    avg_processing = round(sum(proc_times) / len(proc_times)) if proc_times else 0

    return {
        "total_all_time": len(records),
        "total_today": len(today_records),
        "total_this_week": len(week_records),
        "threat_detections": sum(threat_breakdown.values()),
        "threat_breakdown": threat_breakdown,
        "attendance_processed": len(att_records),
        "attendance_breakdown": att_breakdown,
        "category_breakdown": cat_breakdown,
        "daily_volume": daily_volume,
        "avg_processing_time_ms": avg_processing,
    }


@router.get("/school/{school_id}/config")
async def get_school_settings(school_id: str):
    """Get configuration for a specific school."""
    seed_mock_data()
    config = _school_configs.get(school_id)
    if not config:
        raise HTTPException(status_code=404, detail="School not found")
    return {"school_id": school_id, **config}


class SchoolConfigUpdate(BaseModel):
    school_name: Optional[str] = None
    admin_phones: Optional[List[str]] = None
    admin_emails: Optional[List[str]] = None
    police_phone: Optional[str] = None
    police_email: Optional[str] = None
    attendance_line: Optional[str] = None
    webhook_url: Optional[str] = None
    attendance_webhook_url: Optional[str] = None
    alert_keywords: Optional[List[str]] = None
    sensitivity: Optional[str] = None


@router.put("/school/{school_id}/config")
async def update_school_settings(school_id: str, update: SchoolConfigUpdate):
    """Update configuration for a specific school."""
    seed_mock_data()
    if school_id not in _school_configs:
        raise HTTPException(status_code=404, detail="School not found")
    data = update.dict(exclude_none=True)
    _school_configs[school_id].update(data)
    return {"status": "updated", "school_id": school_id, **_school_configs[school_id]}
