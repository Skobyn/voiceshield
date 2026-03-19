# 🛡️ VoiceShield

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**School Voicemail Intelligence System** — Real-time transcription, threat detection, and attendance automation.

## The Problem

A school received a threatening voicemail at 4:30 AM. Nobody checked it until 7:30 AM. Three hours of unnecessary risk. VoiceShield eliminates that gap entirely.

## What It Does

1. **Instant Transcription** — Every voicemail is transcribed the moment it arrives (Deepgram Nova-2 or OpenAI Whisper)
2. **Threat Detection** — AI classifies each message for threat language. Critical threats trigger immediate SMS/email alerts to school admins and local police
3. **Attendance Automation** — Parent call-ins are parsed into structured records (student name, reason, date) and exported to the school's attendance system

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  School Phone   │────▶│   VoiceShield    │────▶│  Notifications  │
│  System (VoIP)  │     │   (Cloud Run)    │     │  SMS / Email    │
│                 │     │                  │     │  Police Alert   │
│  Twilio / SIP   │     │  ┌────────────┐  │     │  Webhook        │
│  RingCentral    │     │  │ Transcribe │  │     └─────────────────┘
│  8x8 / Cisco    │     │  │ (Deepgram) │  │
└─────────────────┘     │  └─────┬──────┘  │     ┌─────────────────┐
                        │  ┌─────▼──────┐  │────▶│  Attendance     │
                        │  │ Classify   │  │     │  CSV / Sheet /  │
                        │  │ (Claude)   │  │     │  Webhook        │
                        │  └─────┬──────┘  │     └─────────────────┘
                        │  ┌─────▼──────┐  │
                        │  │ Alert/Log  │  │     ┌─────────────────┐
                        │  │ (Twilio +  │  │────▶│  Dashboard      │
                        │  │  SendGrid) │  │     │  (Web UI)       │
                        │  └────────────┘  │     └─────────────────┘
                        └──────────────────┘
```

## Quick Start

```bash
# Run locally
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8080

# Test the demo endpoint (no API keys needed for keyword fallback)
curl -X POST http://localhost:8080/demo/classify \
  -H "Content-Type: application/json" \
  -d '{"transcript": "There is a bomb in the school building"}'

# Test an attendance voicemail
curl -X POST http://localhost:8080/demo/classify \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Hi this is Sarahs mom, she wont be in today, shes sick with the flu"}'
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPGRAM_API_KEY` | Recommended | Deepgram API key for transcription |
| `OPENAI_API_KEY` | Fallback | OpenAI API key (Whisper transcription) |
| `ANTHROPIC_API_KEY` | Recommended | Claude API key for classification |
| `TWILIO_ACCOUNT_SID` | For SMS | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | For SMS | Twilio auth token |
| `TWILIO_FROM_NUMBER` | For SMS | Twilio sender number |
| `SENDGRID_API_KEY` | For email | SendGrid API key |
| `USE_FIRESTORE` | Production | Set to "true" for persistent storage |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/webhook/twilio/voicemail` | Twilio voicemail webhook |
| POST | `/webhook/voicemail` | Generic VoIP webhook |
| POST | `/demo/classify` | Demo: classify text directly |
| GET | `/dashboard` | Web dashboard |

## Phone System Integration

### Twilio (Simplest)
Point your Twilio voicemail recording callback URL to `POST /webhook/twilio/voicemail`

### RingCentral / 8x8 / Cisco
Use the generic webhook: configure your PBX to POST to `/webhook/voicemail` with:
```json
{
  "audio_url": "https://your-pbx.com/recordings/123.wav",
  "caller": "+15551234567",
  "called_number": "+15559876543",
  "school_id": "your-school-id"
}
```

### SIP Trunk
Connect via Twilio SIP Trunking to bridge existing PBX systems.

## Multi-Tenant SaaS Model

Each school is a `school_id` with its own:
- Alert contacts (admin phones, emails, police contacts)
- Attendance webhook configuration
- Dashboard access
- Voicemail history

## Deploy

```bash
# Docker
docker build -t voiceshield .
docker run -p 8080:8080 -e DEEPGRAM_API_KEY=xxx voiceshield

# GCP Cloud Run (via Terraform)
cd infra && terraform apply

# GitHub Actions deploys on push to main
```

## License

This project is licensed under the [MIT License](LICENSE). See the [LICENSE](LICENSE) file for details.
