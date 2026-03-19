"""
VoiceShield — Storage Module
Supports Firestore (production) and in-memory (development/demo).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("voiceshield.storage")

USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "false").lower() == "true"

# In-memory storage for demo/development
_voicemail_records: List[Dict[str, Any]] = []
_attendance_records: List[Dict[str, Any]] = []
_school_configs: Dict[str, Dict[str, Any]] = {
    "default": {
        "school_name": "Demo School",
        "admin_phones": [],
        "admin_emails": [],
        "police_phone": None,
        "police_email": None,
        "webhook_url": None,
        "attendance_webhook_url": None,
    },
    "demo-school": {
        "school_name": "Demo School",
        "admin_phones": ["+15551234567"],
        "admin_emails": ["admin@demo-school.example.com"],
        "police_phone": "+15559876543",
        "police_email": "dispatch@local-pd.gov",
        "webhook_url": None,
        "attendance_webhook_url": None,
    },
}


async def store_voicemail_record(school_id: str, record: Dict[str, Any]):
    """Store a processed voicemail record."""
    if USE_FIRESTORE:
        await _firestore_store("voicemails", school_id, record)
    else:
        _voicemail_records.insert(0, record)
        logger.info(f"Stored voicemail record (in-memory): {record.get('recording_sid')}")


async def get_voicemail_records(school_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve voicemail records."""
    if USE_FIRESTORE:
        return await _firestore_query("voicemails", school_id, limit)
    else:
        records = _voicemail_records
        if school_id:
            records = [r for r in records if r.get("school_id") == school_id]
        return records[:limit]


async def store_attendance_record(school_id: str, record):
    """Store a parsed attendance record."""
    data = record.dict() if hasattr(record, "dict") else record
    data["school_id"] = school_id

    if USE_FIRESTORE:
        await _firestore_store("attendance", school_id, data)
    else:
        _attendance_records.insert(0, data)
        logger.info(f"Stored attendance record (in-memory): {data.get('student_name')}")

    # Send to attendance webhook if configured
    config = await get_school_config(school_id)
    webhook = config.get("attendance_webhook_url")
    if webhook:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook, json=data)
                logger.info(f"Attendance record sent to webhook: {webhook}")
        except Exception as e:
            logger.error(f"Failed to send attendance webhook: {e}")


async def get_attendance_records(school_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve attendance records."""
    if USE_FIRESTORE:
        return await _firestore_query("attendance", school_id, limit)
    else:
        records = _attendance_records
        if school_id:
            records = [r for r in records if r.get("school_id") == school_id]
        return records[:limit]


async def get_school_config(school_id: str) -> Dict[str, Any]:
    """Get school configuration."""
    if USE_FIRESTORE:
        return await _firestore_get_config(school_id)
    return _school_configs.get(school_id, _school_configs["default"])


# ──────────────────────────────────────────────
# Firestore Implementation
# ──────────────────────────────────────────────

async def _firestore_store(collection: str, school_id: str, data: dict):
    from google.cloud import firestore
    db = firestore.AsyncClient()
    doc_ref = db.collection("schools").document(school_id).collection(collection).document()
    await doc_ref.set(data)


async def _firestore_query(collection: str, school_id: str = None, limit: int = 50):
    from google.cloud import firestore
    db = firestore.AsyncClient()
    if school_id:
        query = db.collection("schools").document(school_id).collection(collection)
    else:
        query = db.collection_group(collection)
    docs = query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
    return [doc.to_dict() async for doc in docs.stream()]


async def _firestore_get_config(school_id: str):
    from google.cloud import firestore
    db = firestore.AsyncClient()
    doc = await db.collection("schools").document(school_id).get()
    if doc.exists:
        return doc.to_dict()
    return _school_configs["default"]
