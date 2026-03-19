"""
VoiceShield — Transcription Module
Supports Deepgram (primary) and OpenAI Whisper (fallback).
"""

import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger("voiceshield.transcription")

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


async def transcribe_audio_url(audio_url: str) -> str:
    """Transcribe audio from a URL. Tries Deepgram first, falls back to Whisper."""
    if DEEPGRAM_API_KEY:
        try:
            return await _deepgram_transcribe_url(audio_url)
        except Exception as e:
            logger.warning(f"Deepgram failed, falling back to Whisper: {e}")

    if OPENAI_API_KEY:
        return await _whisper_transcribe_url(audio_url)

    raise RuntimeError("No transcription API key configured (DEEPGRAM_API_KEY or OPENAI_API_KEY)")


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe audio from raw bytes."""
    if DEEPGRAM_API_KEY:
        try:
            return await _deepgram_transcribe_bytes(audio_bytes)
        except Exception as e:
            logger.warning(f"Deepgram failed, falling back to Whisper: {e}")

    if OPENAI_API_KEY:
        return await _whisper_transcribe_bytes(audio_bytes, filename)

    raise RuntimeError("No transcription API key configured")


# ──────────────────────────────────────────────
# Deepgram
# ──────────────────────────────────────────────

async def _deepgram_transcribe_url(audio_url: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "url": audio_url,
            },
            params={
                "model": "nova-2",
                "smart_format": "true",
                "punctuate": "true",
                "diarize": "true",
                "language": "en",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return _extract_deepgram_transcript(data)


async def _deepgram_transcribe_bytes(audio_bytes: bytes) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "audio/wav",
            },
            content=audio_bytes,
            params={
                "model": "nova-2",
                "smart_format": "true",
                "punctuate": "true",
                "diarize": "true",
                "language": "en",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return _extract_deepgram_transcript(data)


def _extract_deepgram_transcript(data: dict) -> str:
    try:
        return data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        raise ValueError(f"Unexpected Deepgram response: {data}")


# ──────────────────────────────────────────────
# OpenAI Whisper
# ──────────────────────────────────────────────

async def _whisper_transcribe_url(audio_url: str) -> str:
    """Download audio then send to Whisper."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        audio_resp = await client.get(audio_url)
        audio_resp.raise_for_status()
        return await _whisper_transcribe_bytes(audio_resp.content, "voicemail.wav")


async def _whisper_transcribe_bytes(audio_bytes: bytes, filename: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/wav")},
            data={"model": "whisper-1", "language": "en"},
        )
        resp.raise_for_status()
        return resp.json()["text"]
