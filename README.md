# IIST AdmitBot — AI Admissions Chatbot & Analytics Dashboard

> 24/7 AI-powered bilingual admission chatbot and lead management system for **Indore Institute of Science & Technology (IIST)**, built entirely on free tools.

[![Tests](https://img.shields.io/badge/tests-91%20passing-brightgreen)](#running-tests)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack (All Free)](#tech-stack-all-free)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Admin Dashboard Setup](#admin-dashboard-setup)
- [n8n Automation Workflows](#n8n-automation-workflows)
- [Implementation Phases](#implementation-phases)
- [Running Tests](#running-tests)
- [Deployment](#deployment)
- [Analytics Dashboard](#analytics-dashboard)
- [Security](#security)

---

## Overview

IIST AdmitBot eliminates the 2–6 hour response delays that cost institutions valuable leads. It provides:

| Feature | Benefit |
|---|---|
| 24/7 auto-response (<12 sec) | Zero missed enquiries |
| Bilingual (Hindi + English) | Inclusive, wider reach |
| AI lead scoring (Hot/Warm/Cold) | Counsellors focus on high-intent students |
| Auto lead capture → Google Sheets | No manual data entry |
| Hot-lead WhatsApp alerts | Counsellor notified within seconds |
| Live Looker Studio dashboard | Real-time management visibility |
| 8 automated n8n workflows | Zero manual scheduling |

---

## Architecture

```
Student (WhatsApp / Website)
         │
         ▼
Meta WhatsApp API / Tawk.to
         │  (webhook)
         ▼
   FastAPI Backend  ←──── Groq LLM (bilingual responses)
  (Railway.app)
         │
    ┌────┴────┐
    ▼         ▼
Google     Counsellor
Sheets     WhatsApp Alert
    │
    ▼
 n8n Scheduled Automations
 (reports, reminders, follow-ups)
    │
    ▼
Looker Studio Dashboard
(HOD / Principal)
```

**Data flow:**
1. Student sends WhatsApp/website message
2. Meta API / Tawk.to forwards webhook to FastAPI backend
3. FastAPI builds prompt with IIST knowledge base and calls Groq
4. Groq generates bilingual reply + structured lead data
5. FastAPI sends reply to student (<12 seconds end-to-end)
6. Lead written to Google Sheets (with duplicate detection)
7. If Hot lead → backend sends counsellor WhatsApp alert immediately
8. n8n runs scheduled automations (follow-ups/reports/reminders)
9. Looker Studio reads Google Sheets → dashboard updates live

---

## Architecture Mode

This repository is configured for **Backend-First** operation.

- FastAPI is the single real-time processing engine for incoming messages.
- n8n is used for scheduled and operational workflows only.
- Do **not** run `01-main-bot` and `02-hot-lead-alert` in production with backend webhooks, or you may process the same lead twice.

---

## Tech Stack (All Free)

| Component | Tool | Cost | Purpose |
|---|---|---|---|
| AI / NLP | Groq API | Free tier available | Bilingual responses |
| Automation | n8n (self-hosted) | Free | Core workflow engine |
| Backend | FastAPI + Python | Free | Webhook handler |
| Cloud | Railway.app | Free (500 hrs/mo) | Hosts backend + n8n |
| WhatsApp | Meta WhatsApp Business API | Free (1,000 conv/mo) | Official WA channel |
| Website Widget | Tawk.to | Free forever | Website chat bubble |
| Lead Database | Google Sheets | Free (15 GB) | Lead storage |
| Dashboard | Google Looker Studio | Free | Live analytics |
| Monitoring | UptimeRobot | Free | Prevent Railway sleep |

---

## Project Structure

```
├── backend/
│   ├── app.py                    # FastAPI application (webhooks)
│   ├── config.py                 # Settings from environment variables
│   ├── chatbot/
│   │   ├── ai_client.py          # Groq-first AI client (+ rule-based fallback)
│   │   ├── knowledge_base.py     # IIST course/fee/FAQ content
│   │   ├── language_detector.py  # Hindi/Hinglish/English detection
│   │   └── lead_scorer.py        # Hot/Warm/Cold scoring logic
│   ├── integrations/
│   │   ├── whatsapp.py           # Meta WhatsApp Business API client
│   │   └── google_sheets.py      # Google Sheets lead capture
│   └── workflows/
│       └── counsellor_assignment.py  # Round-robin assignment
├── n8n-workflows/                # n8n JSON workflow exports
│   ├── 01-main-bot.json          # Core bot (WhatsApp + Website)
│   ├── 02-hot-lead-alert.json    # Counsellor alert on Hot lead
│   ├── 03-48hr-followup.json     # 48-hour silence follow-up
│   ├── 04-daily-hod-report.json  # Daily 8 AM HOD WhatsApp report
│   ├── 05-weekly-principal-report.json  # Monday 9 AM Principal report
│   ├── 06-deadline-reminder.json # June 23 bulk reminder
│   ├── 07-counsellor-assignment.json    # Load-balanced assignment
│   └── 08-enrolment-trigger.json # Congrats + doc checklist
├── website/
│   └── chat-widget.html          # Tawk.to widget snippet
├── tests/                        # Pytest unit tests (54 tests)
├── .env.example                  # Environment variables template
├── docker-compose.yml            # Local dev: n8n + FastAPI
├── Dockerfile                    # FastAPI container
└── railway.toml                  # Railway.app deployment config
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/anshika-codes-AI/AI-Admissions-Chatbot-Admissions-Analytics-Dashboard
cd AI-Admissions-Chatbot-Admissions-Analytics-Dashboard
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 3. Run locally

```bash
uvicorn backend.app:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 4. Run with Docker (n8n + FastAPI)

```bash
docker-compose up -d
# n8n at http://localhost:5678
# FastAPI at http://localhost:8000
```

---

## Configuration

Copy `.env.example` to `.env` and fill in all values:

```env
# Required for bot to respond
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key

# Required for WhatsApp channel
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_ACCESS_TOKEN=your_permanent_token
WHATSAPP_VERIFY_TOKEN=your_custom_string   # Any string you choose

# Required for lead capture
GOOGLE_SHEETS_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# Required for counsellor alerts
COUNSELLOR_NUMBERS=+919876543210,+919876543211
```

All credentials are stored as Railway environment variables — never in code.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (UptimeRobot pings this) |
| `GET` | `/webhook/whatsapp` | Meta webhook verification handshake |
| `POST` | `/webhook/whatsapp` | Receive incoming WhatsApp messages |
| `POST` | `/webhook/tawkto` | Receive Tawk.to website chat messages |
| `GET` | `/admin` | Admin dashboard UI |
| `POST` | `/api/admin/auth/login` | Create admin session (username/password) |
| `GET` | `/api/admin/auth/me` | Current admin session and role |
| `POST` | `/api/admin/auth/logout` | Clear admin session |
| `GET` | `/api/admin/overview` | Dashboard data API (session role or service bearer token) |

Admin roles:
- `admin`: full dashboard access
- `viewer`: read-only dashboard access

Set `ADMIN_USERS_JSON` in `.env` to manage credentials and roles.
Set `N8N_API_URL` + `N8N_API_KEY` to enable live runtime workflow polling.

**Interactive docs:** `http://localhost:8000/docs` (Swagger UI)

---

## Admin Dashboard Setup

**For a complete, detailed setup guide on the professional admin dashboard with session-based authentication, role-based access, live n8n workflow monitoring, and analytics charts, see [ADMIN_SETUP.md](ADMIN_SETUP.md).**

### Quick Admin Dashboard Features

✅ **Session-Based Authentication** — Username/password login with secure cookies
✅ **Role-Based Access** — Admin (full access) and Viewer (read-only) roles
✅ **Live Workflow Monitoring** — Real-time n8n execution status and metrics
✅ **Analytics Charts** — 24h lead trend line chart + counsellor performance bar chart
✅ **Integration Health** — Status of Groq, WhatsApp, Telegram, Google Sheets, n8n, Tawk.to
✅ **KPI Dashboard** — Real-time metrics (messages, hot leads, assignments, response time, uptime)
✅ **Auto-Refresh** — Dashboard updates every 15 seconds

### Quick Start (5 minutes)

1. **Set env vars** (add to `.env`):
   ```env
   ADMIN_SESSION_SECRET=your_32_char_random_secret
   ADMIN_USERS_JSON=[{"username":"admin","password":"Pass123","role":"admin"}]
   N8N_API_URL=http://localhost:5678
   N8N_API_KEY=your_n8n_api_key
   ```

2. **Run backend:**
   ```bash
   uvicorn backend.app:app --reload
   ```

3. **Open dashboard:**
   - Visit `http://localhost:8000/admin`
   - Login with `admin` / `Pass123`
   - View workflows, KPIs, and charts

**→ [Full Setup Guide](ADMIN_SETUP.md)**

---

## n8n Automation Workflows

Import JSON files from `n8n-workflows/` into your n8n instance:

| Workflow | Trigger | Phase |
|---|---|---|
| `01-main-bot` | WhatsApp/website message | Legacy (keep disabled in backend-first mode) |
| `02-hot-lead-alert` | Lead scored Hot | Legacy (keep disabled in backend-first mode) |
| `03-48hr-followup` | 48 hrs silence | 2 |
| `04-daily-hod-report` | Every day 8 AM | 4 |
| `05-weekly-principal-report` | Every Monday 9 AM | 4 |
| `06-deadline-reminder` | June 23 (7 days before) | 4 |
| `07-counsellor-assignment` | New hot lead | Optional (only if assignment moved from backend to n8n) |
| `08-enrolment-trigger` | Status → Enrolled | 4 |

**Import steps:** n8n → Workflows → Import → select JSON file → Save → Activate

---

## Implementation Phases

### Phase 1 — Foundation ✅
- [ ] Deploy n8n on Railway.app
- [ ] Configure Groq API key
- [ ] Build main bot workflow (`01-main-bot.json`)
- [ ] Test 50 bilingual conversations

### Phase 2 — Lead Management
- [ ] Create Google Sheets with lead schema
- [ ] Activate hot-lead alert workflow (`02-hot-lead-alert.json`)
- [ ] Activate 48-hr follow-up (`03-48hr-followup.json`)
- [ ] Train counsellors on Google Sheets

### Phase 3 — Multi-Channel Integration
- [ ] Set up Tawk.to website widget (`website/chat-widget.html`)
- [ ] Complete Meta WhatsApp API verification
- [ ] Configure source attribution tagging

### Phase 4 — Analytics & Full Launch
- [ ] Connect Google Sheets to Looker Studio
- [ ] Activate HOD daily report (`04-daily-hod-report.json`)
- [ ] Activate Principal weekly report (`05-weekly-principal-report.json`)
- [ ] Full load test (50+ simultaneous conversations)
- [ ] Launch 🚀

---

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=term-missing
```

**54 tests** covering:
- Language detection (Hindi / Hinglish / English)
- Lead scoring (Hot / Warm / Cold)
- WhatsApp webhook payload parsing
- AI response parsing
- Counsellor round-robin assignment
- FastAPI endpoints (health, verify, webhook)

---

## Deployment

### Render (Recommended for Backend-Only Deploys)

This repository can be deployed on Render without n8n, WhatsApp, or Google Sheets.
That is the simplest path for a `website + Telegram` launch.

1. Push the repo to GitHub.
2. In Render, create a new Web Service from the repo.
3. Use these settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/health`
4. Add the minimum required environment variables:
   - `AI_PROVIDER=groq`
   - `GROQ_API_KEY=your_real_groq_key`
   - `TELEGRAM_BOT_TOKEN=your_real_telegram_token`
   - `TELEGRAM_WEBHOOK_SECRET=your_random_secret`
   - `API_SECRET_KEY=your_random_secret`
5. Leave these blank if they are not ready yet:
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_ACCESS_TOKEN`
   - `GOOGLE_SHEETS_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
   - `N8N_WEBHOOK_URL`

You can also use the provided `render.yaml` blueprint for a one-click baseline deploy.

### Telegram Webhook After Deploy

After Render gives you a public URL, configure Telegram with:

`https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://your-render-domain/webhook/telegram/<TELEGRAM_WEBHOOK_SECRET>`

### Optional: Railway

Railway remains supported through `railway.toml`, but Render is the simpler choice for the current backend-only rollout.

### Uptime Monitoring

1. Create account at [uptimerobot.com](https://uptimerobot.com)
2. Add HTTP(S) monitor → `https://your-domain/health`
3. Set interval: every 5 minutes
4. Add email alert for downtime

---

## Analytics Dashboard

**Google Looker Studio Setup:**

1. Go to [lookerstudio.google.com](https://lookerstudio.google.com)
2. Create New Report → Add Data → Google Sheets
3. Select your IIST Leads sheet
4. Build these visualisations:
   - **KPI Scorecards:** Total Enquiries, Hot Leads, Enrolled Today
   - **Bar Chart:** Source-wise lead volume (WhatsApp/Website/Instagram/Google)
   - **Line Chart:** Daily enquiry trend (30 days)
   - **Table:** Counsellor performance (leads, conversions)
   - **Geo Chart:** City-wise lead heatmap (MP region)
   - **Funnel:** Enquiry → Hot → Contacted → Enrolled

---

## Google Sheets Lead Schema

| Column | Source | Example |
|---|---|---|
| Timestamp | Automatic | 2026-03-02 14:32:11 |
| Student Name | AI extracted | Rahul Kumar |
| Phone Number | WhatsApp metadata | +919876543210 |
| City | AI extracted | Bhopal |
| Course Interest | AI extracted | B.Tech CSE |
| JEE / 12th Score | AI extracted | 78 percentile |
| Source Channel | Automatic | WhatsApp |
| Lead Score | AI scoring | Hot |
| Assigned To | Counsellor manual | Ritu Sharma |
| Lead Status | Counsellor manual | Contacted |
| Notes | Counsellor manual | Called, interested |
| Last Updated | Automatic | 2026-03-02 16:45:00 |
| Conversation History | Automatic | Full chat transcript |

---

## Security

- All student data in **IIST-owned Google Sheets** — no third-party CRM
- API credentials stored as **platform environment variables** — never in code
- **No student PII** sent to AI models — only message text and knowledge base
- WhatsApp access token stored separately — rotatable in 10 minutes if compromised
- Google Sheets access restricted to admission team via Google Workspace
- Conversation data retained 30 days per institutional data policy

---

## Sample Interactions

**English:**
> Student: "What are the CSE admission requirements?"
> AdmitBot: "For B.Tech CSE at IIST, you need JEE Main 85+ percentile OR 12th PCM 75%+. 🎓 Annual fees are ₹85,000. We also have merit scholarships (25% off for 95%ile+)! Would you like to know about the admission process? 😊"

**Hindi/Hinglish:**
> Student: "Bhai CSE mein admission kaise hoga? Mera 78 percentile hai."
> AdmitBot: "CSE ke liye 85 percentile chahiye. Aapka 78 percentile hai — aap ECE (70+ required) ya IT (75+ required) ke liye eligible hain! 🎓 Annual fees ₹82,000 hai. Kya aap scholarship ke baare mein jaanna chahenge?"

---

*Built with ❤️ for IIST — making every student enquiry count.*
