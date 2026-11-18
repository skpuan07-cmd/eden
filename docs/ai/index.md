# Sahana Eden AI Modules

AI-powered features for disaster management, integrated with Sahana Eden (web2py).

## Documentation Index

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Quick start + 10 use case overview |
| [INSTALL_SUMMARY.md](INSTALL_SUMMARY.md) | Step-by-step installation guide |
| [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md) | Full system docs: architecture, DB schema, patches, troubleshooting |
| [RECOMMENDATIONS.md](RECOMMENDATIONS.md) | Modernization recommendations: AI, Cyber Security, PDPA compliance |

## Quick Start

```bash
# 1. Copy AI module files into your Eden install
cp controllers/ai*.py                 ~/eden/controllers/
cp models/zz_ai_tables.py             ~/eden/models/
mkdir -p ~/eden/modules/s3
cp modules/s3/ai_client.py            ~/eden/modules/s3/
cp modules/s3/ai_ocr_openthai.py      ~/eden/modules/s3/
cp -r views/ai*                       ~/eden/views/

# 2. Restart web2py
kill -TERM $(cat ~/eden-logs/web2py.pid)
python3 web2py.py --no_gui -a your_password --ip 0.0.0.0 --port 3000

# 3. Visit /eden/ai/ (must be logged in as admin)
```

## The 10 AI Use Cases

| # | Feature | URL | Auth |
|---|---------|-----|------|
| 1 | Chatbot (RAG) | `/eden/ai_chat/` | Public (PDPA consent) |
| 2 | OCR + Data Extraction | `/eden/ai_ocr/` | Public (consent required) |
| 3 | Predictive Analytics | `/eden/ai_analytics/` | Public |
| 4 | Imagery Analysis | `/eden/ai_imagery/` | Public |
| 5 | Translation | `/eden/ai_translate/` | Admin |
| 6 | Natural Language Query | `/eden/ai_query/` | Admin |
| 7 | Code Assistance | (docs) | N/A |
| 8 | RAG Knowledge Base | `/eden/ai_kb/` | Admin |
| 9 | Voice Interface | `/eden/ai_voice/` | Public |
| 10 | Content Moderation | `/eden/ai_moderation/` | Admin |

## Configuration

### z-ai CLI (required for all features)
The `z-ai-web-dev-sdk` package must be installed and `z-ai` CLI in PATH. This provides:
- `chat` — LLM text completions (glm-4-plus)
- `vision` — Vision model (glm-5.3-flash) for OCR and image analysis
- `asr` — Speech to text (Whisper)
- `tts` — Text to speech

### OpenThai 2.1 OCR (optional, recommended for Thai ID cards)
Get an API key from https://iapp.co.th/ and set as env var:
```bash
export IAPP_API_KEY="iapp_live_your_key_here"
```

The launcher script `scripts/launch_eden_daemon.py` automatically loads env vars from `/etc/eden/env` (root-only readable) on startup.

### Prophet (for Use Case 3 — Predictive Analytics)
```bash
pip install prophet pandas
```

## PDPA Compliance

- Chatbot (Use Case 1) and OCR (Use Case 2) require explicit user consent before processing
- All AI calls logged with model, latency, IP, and consent flag in `ai_*_log` tables
- OpenThai API key loaded from env file (never committed to git)
- NLQ (Use Case 6) whitelist restricts accessible controllers — sensitive tables (`auth_user`, `dvr_case`, `med_patient`) are blocked
- Content Moderation (Use Case 10) auto-detects PDPA violations (Thai ID numbers, phone numbers)

See [RECOMMENDATIONS.md](RECOMMENDATIONS.md) for full PDPA compliance guidance.

## License

Same as Sahana Eden (MIT).
