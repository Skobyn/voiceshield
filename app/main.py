"""
VoiceShield — School Voicemail Intelligence System
Main FastAPI application.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from transcription import transcribe_audio_url, transcribe_audio_bytes
from classifier import classify_voicemail, ThreatLevel
from alerting import send_threat_alerts
from attendance import parse_attendance_record
from storage import (
    store_voicemail_record,
    get_voicemail_records,
    get_school_config,
    store_attendance_record,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voiceshield")

app = FastAPI(
    title="VoiceShield",
    description="School Voicemail Intelligence — Transcription, Threat Detection, Attendance Automation",
    version="0.1.0",
)

# ──────────────────────────────────────────────
# Dashboard API + Static Files
# ──────────────────────────────────────────────
from dashboard_api import router as dashboard_router
app.include_router(dashboard_router)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "voiceshield", "version": "0.1.0"}


# ──────────────────────────────────────────────
# Twilio Webhook — Incoming Voicemail
# ──────────────────────────────────────────────

@app.post("/webhook/twilio/voicemail")
async def twilio_voicemail_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio calls this when a new voicemail recording is available.
    Expects form data with RecordingUrl, RecordingSid, CallSid, From, To, etc.
    """
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    recording_sid = form.get("RecordingSid")
    call_sid = form.get("CallSid")
    caller = form.get("From", "unknown")
    called_number = form.get("To", "unknown")

    if not recording_url:
        raise HTTPException(status_code=400, detail="Missing RecordingUrl")

    # Twilio recordings are available as .wav
    audio_url = f"{recording_url}.wav"

    logger.info(f"New voicemail: {recording_sid} from {caller} to {called_number}")

    # Process in background so Twilio gets a fast 200
    background_tasks.add_task(
        process_voicemail,
        audio_url=audio_url,
        recording_sid=recording_sid,
        call_sid=call_sid,
        caller=caller,
        called_number=called_number,
    )

    return JSONResponse({"status": "accepted", "recording_sid": recording_sid})


# ──────────────────────────────────────────────
# Generic Webhook — SIP/PBX integration
# ──────────────────────────────────────────────

class GenericVoicemailPayload(BaseModel):
    audio_url: str
    caller: str = "unknown"
    called_number: str = "unknown"
    school_id: str = "default"
    recording_id: Optional[str] = None
    timestamp: Optional[str] = None


@app.post("/webhook/voicemail")
async def generic_voicemail_webhook(payload: GenericVoicemailPayload, background_tasks: BackgroundTasks):
    """
    Generic webhook for non-Twilio VoIP systems.
    Any PBX/SIP system can POST here with an audio URL.
    """
    recording_id = payload.recording_id or f"gen-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    logger.info(f"Generic voicemail: {recording_id} from {payload.caller}")

    background_tasks.add_task(
        process_voicemail,
        audio_url=payload.audio_url,
        recording_sid=recording_id,
        call_sid=None,
        caller=payload.caller,
        called_number=payload.called_number,
        school_id=payload.school_id,
    )

    return JSONResponse({"status": "accepted", "recording_id": recording_id})


# ──────────────────────────────────────────────
# Demo Endpoint — Test with text input
# ──────────────────────────────────────────────

class DemoPayload(BaseModel):
    transcript: str
    caller: str = "+15551234567"
    called_number: str = "+15559876543"
    school_id: str = "demo-school"


@app.post("/demo/classify")
async def demo_classify(payload: DemoPayload):
    """
    Demo endpoint: skip transcription, directly classify a transcript.
    Useful for testing threat detection and attendance parsing without audio.
    """
    classification = await classify_voicemail(payload.transcript)

    result = {
        "transcript": payload.transcript,
        "classification": classification.dict(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if classification.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
        result["alerts_triggered"] = True
        result["alert_details"] = "Would notify: school admin + police"

    if classification.is_attendance:
        attendance = await parse_attendance_record(payload.transcript)
        result["attendance_record"] = attendance.dict() if attendance else None

    return result


# ──────────────────────────────────────────────
# Dashboard — Simple HTML view
# ──────────────────────────────────────────────

@app.get("/dashboard")
async def dashboard():
    """Serve the full VoiceShield dashboard UI."""
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


# ──────────────────────────────────────────────
# Core Processing Pipeline
# ──────────────────────────────────────────────

async def process_voicemail(
    audio_url: str,
    recording_sid: str,
    call_sid: Optional[str],
    caller: str,
    called_number: str,
    school_id: str = "default",
):
    """
    Full voicemail processing pipeline:
    1. Transcribe audio
    2. Classify content (threat detection)
    3. If threat: send alerts
    4. If attendance: parse and store structured record
    5. Store everything
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Step 1: Transcribe
        logger.info(f"[{recording_sid}] Transcribing...")
        transcript = await transcribe_audio_url(audio_url)
        logger.info(f"[{recording_sid}] Transcript: {transcript[:100]}...")

        # Step 2: Classify
        logger.info(f"[{recording_sid}] Classifying...")
        classification = await classify_voicemail(transcript)
        logger.info(f"[{recording_sid}] Classification: threat={classification.threat_level}, attendance={classification.is_attendance}")

        # Step 3: Threat alerting
        if classification.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            logger.warning(f"[{recording_sid}] ⚠️ THREAT DETECTED: {classification.threat_level}")
            school_config = await get_school_config(school_id)
            await send_threat_alerts(
                school_config=school_config,
                transcript=transcript,
                threat_level=classification.threat_level,
                caller=caller,
                recording_sid=recording_sid,
                timestamp=timestamp,
            )

        # Step 4: Attendance parsing
        attendance_record = None
        if classification.is_attendance:
            logger.info(f"[{recording_sid}] Parsing attendance record...")
            attendance_record = await parse_attendance_record(transcript)
            if attendance_record:
                await store_attendance_record(school_id, attendance_record)

        # Step 5: Store full record
        await store_voicemail_record(
            school_id=school_id,
            record={
                "recording_sid": recording_sid,
                "call_sid": call_sid,
                "caller": caller,
                "called_number": called_number,
                "audio_url": audio_url,
                "transcript": transcript,
                "threat_level": classification.threat_level.value,
                "threat_keywords": classification.threat_keywords,
                "category": classification.category,
                "is_attendance": classification.is_attendance,
                "attendance_record": attendance_record.dict() if attendance_record else None,
                "confidence": classification.confidence,
                "timestamp": timestamp,
            },
        )

        logger.info(f"[{recording_sid}] ✅ Processing complete")

    except Exception as e:
        logger.error(f"[{recording_sid}] ❌ Processing failed: {e}", exc_info=True)
        # Store error record
        await store_voicemail_record(
            school_id=school_id,
            record={
                "recording_sid": recording_sid,
                "caller": caller,
                "audio_url": audio_url,
                "error": str(e),
                "timestamp": timestamp,
                "threat_level": "unknown",
                "category": "error",
            },
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
