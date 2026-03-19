"""
VoiceShield — Alerting Module
Sends notifications via email (SendGrid), SMS (Twilio), and webhook.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

import httpx

from classifier import ThreatLevel

logger = logging.getLogger("voiceshield.alerting")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "alerts@voiceshield.app")


async def send_threat_alerts(
    school_config: Dict[str, Any],
    transcript: str,
    threat_level: ThreatLevel,
    caller: str,
    recording_sid: str,
    timestamp: str,
):
    """
    Send threat alerts to all configured recipients.
    school_config should contain:
      - admin_phones: list of phone numbers
      - admin_emails: list of email addresses
      - police_phone: local PD non-emergency or dispatch number
      - police_email: optional police notification email
      - webhook_url: optional webhook for custom integrations
    """
    level_emoji = {
        ThreatLevel.HIGH: "⚠️",
        ThreatLevel.CRITICAL: "🚨",
    }.get(threat_level, "⚠️")

    alert_message = (
        f"{level_emoji} VOICESHIELD THREAT ALERT {level_emoji}\n\n"
        f"Threat Level: {threat_level.value.upper()}\n"
        f"Time: {timestamp}\n"
        f"Caller: {caller}\n"
        f"Recording ID: {recording_sid}\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"— VoiceShield Automated Alert"
    )

    email_subject = f"{level_emoji} VoiceShield: {threat_level.value.upper()} Threat Detected"

    # SMS to school admins
    admin_phones = school_config.get("admin_phones", [])
    for phone in admin_phones:
        try:
            await _send_sms(phone, alert_message)
            logger.info(f"SMS alert sent to {phone}")
        except Exception as e:
            logger.error(f"Failed to SMS {phone}: {e}")

    # Email to school admins
    admin_emails = school_config.get("admin_emails", [])
    for email in admin_emails:
        try:
            await _send_email(email, email_subject, alert_message)
            logger.info(f"Email alert sent to {email}")
        except Exception as e:
            logger.error(f"Failed to email {email}: {e}")

    # Notify police (CRITICAL threats)
    if threat_level == ThreatLevel.CRITICAL:
        police_phone = school_config.get("police_phone")
        if police_phone:
            try:
                await _send_sms(police_phone, alert_message)
                logger.info(f"Police SMS alert sent to {police_phone}")
            except Exception as e:
                logger.error(f"Failed to notify police via SMS: {e}")

        police_email = school_config.get("police_email")
        if police_email:
            try:
                await _send_email(police_email, email_subject, alert_message)
                logger.info(f"Police email alert sent to {police_email}")
            except Exception as e:
                logger.error(f"Failed to notify police via email: {e}")

    # Webhook (for Slack, Teams, PagerDuty, etc.)
    webhook_url = school_config.get("webhook_url")
    if webhook_url:
        try:
            await _send_webhook(webhook_url, {
                "event": "threat_detected",
                "threat_level": threat_level.value,
                "caller": caller,
                "transcript": transcript,
                "recording_sid": recording_sid,
                "timestamp": timestamp,
            })
            logger.info(f"Webhook alert sent to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


async def _send_sms(to: str, body: str):
    """Send SMS via Twilio."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning(f"Twilio not configured — would send SMS to {to}")
        return

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": TWILIO_FROM_NUMBER,
                "To": to,
                "Body": body[:1600],  # Twilio SMS limit
            },
        )
        resp.raise_for_status()


async def _send_email(to: str, subject: str, body: str):
    """Send email via SendGrid."""
    if not SENDGRID_API_KEY:
        logger.warning(f"SendGrid not configured — would email {to}")
        return

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": SENDGRID_FROM_EMAIL},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
        )
        resp.raise_for_status()


async def _send_webhook(url: str, payload: dict):
    """Send webhook POST."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
