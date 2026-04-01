# Admin Dashboard Setup Guide

> Complete guide to set up, configure, and run the IIST AdmitBot professional admin dashboard with session-based authentication, role-based access, live n8n workflow monitoring, and analytics charts.

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Local Development Setup](#local-development-setup)
3. [Admin Authentication Setup](#admin-authentication-setup)
4. [n8n Live Polling Configuration](#n8n-live-polling-configuration)
5. [Running the Dashboard Locally](#running-the-dashboard-locally)
6. [Production Deployment](#production-deployment)
7. [Feature Guide: How to Use the Dashboard](#feature-guide-how-to-use-the-dashboard)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## System Requirements

### For Local Development

- **Python:** 3.10 or higher
- **Node.js & npm:** (optional, only if running local n8n without Docker)
- **Docker & Docker Compose:** (recommended for n8n integration)
- **Git:** (to clone the repository)

### For Production

- **Cloud Platform:** Railway.app, Render, or any Docker-capable hosting
- **n8n Instance:** Self-hosted or managed (required for live workflow polling)
- **Database:** Not required (in-memory metrics by default)
- **SSL/TLS Certificate:** Required for production /admin endpoint

---

## Local Development Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/anshika-codes-AI/IIST-AdmitBot
cd IIST-AdmitBot
```

### Step 2: Create Python Virtual Environment

#### On Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### On macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Key dependencies included:**
- `fastapi` — Backend web framework
- `uvicorn` — ASGI server
- `groq` — Groq API client (Groq-only mode)
- `itsdangerous` — Session token signing
- `requests` — HTTP client for n8n polling
- `pytest` — Testing framework

### Step 4: Configure Environment Variables

Copy the template:

```bash
cp .env.example .env
```

Edit `.env` with your configuration. At minimum, add:

```env
# === GROQ AI (Required) ===
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_actual_groq_api_key_here

# === Session & Admin Auth (Required for Dashboard) ===
ADMIN_SESSION_SECRET=your_super_secret_random_string_min_32_chars
ADMIN_USERS_JSON=[{"username":"admin","password":"SecureAdminPass123","role":"admin"},{"username":"viewer","password":"ViewerPass456","role":"viewer"}]

# === n8n Live Polling (Optional but Recommended) ===
N8N_API_URL=http://localhost:5678
N8N_API_KEY=your_n8n_api_key

# === API Security ===
API_SECRET_KEY=your_api_secret_key_for_webhook_validation

# === Chatbot Features (Configure as needed) ===
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_ACCESS_TOKEN=your_whatsapp_token
WHATSAPP_VERIFY_TOKEN=any_verify_string_you_choose

TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_WEBHOOK_SECRET=your_telegram_secret

# === Lead Capture (Optional) ===
GOOGLE_SHEETS_ID=your_google_sheets_id
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
```

**Generate a strong session secret:**

```bash
# On Windows PowerShell
[System.Convert]::ToBase64String((1..32 | ForEach-Object { [byte](Get-Random -Maximum 256) }))

# On macOS / Linux
openssl rand -base64 32
```

### Step 5: Verify Installation

```bash
# Check Python version
python --version

# Check all dependencies installed
pip list | grep -E "fastapi|uvicorn|groq|itsdangerous"

# Run basic tests
pytest tests/test_app_endpoints.py -v
```

---

## Admin Authentication Setup

### Understanding Admin Users & Roles

The admin dashboard uses **cookie-based session authentication** with two predefined roles:

| Role | Permissions | Use Case |
|---|---|---|
| `admin` | Full dashboard access, all metrics visible | Admin, DevOps, Manager |
| `viewer` | Read-only dashboard access | HOD, Principal, External auditor |

### Creating Admin Users

Admin users are defined in a JSON format in the `.env` file. Each user has:
- `username` — Unique login name
- `password` — Plaintext (consider bcrypt upgrade for production)
- `role` — Either `admin` or `viewer`

#### Format

```json
[
  {
    "username": "admin",
    "password": "SecureAdminPass123",
    "role": "admin"
  },
  {
    "username": "ritu_sharma",
    "password": "CounsellorPass456",
    "role": "viewer"
  },
  {
    "username": "principal",
    "password": "PrincipalPass789",
    "role": "viewer"
  }
]
```

#### Adding Users to .env

Escape the JSON properly in `.env`:

```env
ADMIN_USERS_JSON=[{"username":"admin","password":"SecureAdminPass123","role":"admin"},{"username":"ritu_sharma","password":"CounsellorPass456","role":"viewer"},{"username":"principal","password":"PrincipalPass789","role":"viewer"}]
```

### Session Configuration

| Setting | Default | Purpose |
|---|---|---|
| `ADMIN_SESSION_SECRET` | (required) | Cryptographic key for session tokens |
| `SESSION_COOKIE_NAME` | `admin_session` | Browser cookie name |
| `SESSION_COOKIE_MAX_AGE` | `86400` (24h) | Auto-logout after 24 hours |
| `SESSION_COOKIE_SECURE` | `True` (prod only) | HTTPS-only (set to False for local dev) |
| `SESSION_COOKIE_HTTPONLY` | `True` | Prevent JavaScript access |

#### Customizing Session in Code

If you need to adjust session timeout or cookie name, edit [backend/app.py](backend/app.py):

```python
# Around line 50-60
SESSION_CONFIG = {
    "secret": settings.ADMIN_SESSION_SECRET,
    "cookie": {
        "key": "admin_session",
        "max_age": 86400,  # Change to 3600 for 1 hour, etc.
        "secure": False,   # Set to True in production with HTTPS
        "httponly": True,
    },
}
```

---

## n8n Live Polling Configuration

### Prerequisites

You must have n8n running and accessible. Options:

#### Option A: Local n8n with Docker (Easiest)

```bash
docker-compose up -d
# n8n runs at http://localhost:5678
```

#### Option B: Self-Hosted n8n on Server

If n8n is already running on your server:
- Note the base URL (e.g., `https://n8n.yourserver.com`)
- Obtain the API key from n8n settings

#### Option C: n8n Cloud (n8n.cloud)

If using n8n cloud:
- Base URL is `https://n8n.cloud`
- API key available in account settings

### Retrieving n8n API Credentials

1. Open n8n at `http://localhost:5678` (or your n8n URL)
2. Click **Settings** (⚙️ icon, bottom-left)
3. Go to **API** tab
4. Copy the **API Key** (long string starting with `n8n_...`)
5. Note the **n8n Base URL**

### Adding Credentials to .env

```env
# n8n Connection (Required for live workflow polling)
N8N_API_URL=http://localhost:5678
N8N_API_KEY=n8n_your_actual_api_key_here
```

#### Example with Remote n8n

```env
N8N_API_URL=https://n8n.example.com
N8N_API_KEY=n8n_1a2b3c4d5e6f7g8h9i0j
```

### Verifying n8n Connection

Once backend is running, test the n8n API integration:

```bash
# Check if n8n connection works
curl -H "Authorization: Bearer $N8N_API_KEY" \
  http://localhost:5678/api/v1/workflows
```

Or check the dashboard `/api/admin/overview` endpoint:

```bash
curl -H "Cookie: admin_session=..." \
  http://localhost:8000/api/admin/overview
```

Look for `n8n_status` in the response — should be `"connected"`.

### What Metrics Are Captured from n8n

When connected, the dashboard displays:

- **n8n Connectivity:** Online/Offline status
- **Total Workflows:** Count of workflows in n8n
- **Active Workflows:** How many are enabled
- **Executions (24h):** Success and failure counts
- **Workflow Details Table:**
  - Workflow name
  - Enabled/disabled status
  - Success count (24h)
  - Failure count (24h)
  - Last execution time

### Troubleshooting n8n Connection

**Problem:** Dashboard shows `"n8n_status": "disconnected"`

**Solution:**
1. Verify n8n is running: `curl http://localhost:5678/health`
2. Check API key is correct: `curl -H "Authorization: Bearer $N8N_API_KEY" http://localhost:5678/api/v1/user`
3. Check `.env` file has correct `N8N_API_URL` and `N8N_API_KEY`
4. Restart backend: `uvicorn backend.app:app --reload`

---

## Running the Dashboard Locally

### Start the Backend Server

```bash
# From project root with .venv activated
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Access the Dashboard

Open your browser and go to:

```
http://localhost:8000/admin
```

### First Login

Use credentials from your `.env` `ADMIN_USERS_JSON`:

- **Username:** `admin`
- **Password:** `SecureAdminPass123` (or whatever you set)

### Expected Dashboard Screens

#### 1. Login Screen
- Simple username/password form
- "Remember me" option (optional)

#### 2. Dashboard Main View (After Login)
- **Top KPI Cards:**
  - Total Messages
  - Hot Leads (24h)
  - Counsellor Assignments
  - Response Time (avg)
  - Channel Split (pie)
  - Session Uptime

- **Integration Health Panel:**
  - Groq API (always Groq-only)
  - WhatsApp (configured/unconfigured)
  - Telegram (configured/unconfigured)
  - Google Sheets (connected/disconnected)
  - n8n (connected/disconnected)

- **Workflow Matrix Table:**
  - Workflow name
  - Recommended status (enable/disable)
  - Current status (✓/✗)

- **Charts:**
  - **24h Lead Trend** — Line chart showing hourly message count
  - **Counsellor Performance** — Bar chart showing assignments per counsellor

#### 3. Auto-Refresh
Dashboard refreshes every 15 seconds automatically.

### Logout

Click **Logout** in top-right corner to clear session and return to login screen.

---

## Production Deployment

### Deployment on Railway.app (Recommended)

Railway is the simplest option with automatic Docker support and environment variable management.

#### Step 1: Prepare Your Repository

Ensure these files are in root:
- `.env.example` — Template for environment variables
- `requirements.txt` — Python dependencies
- `Dockerfile` — Container definition
- `backend/app.py` — Main FastAPI app

#### Step 2: Push to GitHub

```bash
git add .
git commit -m "Ready for Railway deployment"
git push origin master
```

#### Step 3: Connect Railway to GitHub

1. Go to [railway.app](https://railway.app)
2. Sign up / log in with GitHub
3. Click **New Project** → **Deploy from GitHub repo**
4. Select your repo
5. Railway automatically detects `Dockerfile` and deploys

#### Step 4: Add Environment Variables

In Railway dashboard:

1. Go to **Variables** tab
2. Add all required `.env` settings:

```
AI_PROVIDER=groq
GROQ_API_KEY=[your groq key]
ADMIN_SESSION_SECRET=[your 32-char secret]
ADMIN_USERS_JSON=[...]
N8N_API_URL=[your n8n url]
N8N_API_KEY=[your n8n key]
API_SECRET_KEY=[your api secret]
WHATSAPP_PHONE_NUMBER_ID=[if using WhatsApp]
WHATSAPP_ACCESS_TOKEN=[if using WhatsApp]
... (other integrations as needed)
```

#### Step 5: Verify Deployment

Once Railway finishes build:
- Visit your public URL: `https://your-railway-app.up.railway.app/health`
- Should return: `{"status":"ok"}`

#### Step 6: Access Admin Dashboard

- URL: `https://your-railway-app.up.railway.app/admin`
- Login with credentials from `ADMIN_USERS_JSON`

### Deployment on Render

Render also supports Docker deployments:

1. Go to [render.com](https://render.com)
2. Create new **Web Service**
3. Connect GitHub repo
4. Choose **Docker** as runtime
5. Add all environment variables
6. Deploy

Your admin URL: `https://your-render-app.onrender.com/admin`

### Environment Variables Checklist

Before deploying to production, ensure these are set:

- ✅ `AI_PROVIDER=groq` (must be groq)
- ✅ `GROQ_API_KEY` (valid Groq API key)
- ✅ `ADMIN_SESSION_SECRET` (32+ random characters)
- ✅ `ADMIN_USERS_JSON` (valid JSON with at least one admin user)
- ✅ `API_SECRET_KEY` (for webhook validation)
- ✅ `SESSION_COOKIE_SECURE=True` (production only, enables HTTPS-only)
- ✅ `ENVIRONMENT=production` (optional, helps with debugging settings)
- ⚠️ `N8N_API_URL` & `N8N_API_KEY` (optional, but required for workflow monitoring)

### SSL/TLS Certificate

**For production HTTPS:**

Railway and Render provide free SSL certificates automatically. If self-hosting, use:

```bash
# Using Let's Encrypt (free)
certbot certonly --standalone -d yourdomain.com
```

---

## Feature Guide: How to Use the Dashboard

### Authentication Flow

1. **First Visit:** `/admin` redirects to login form
2. **Enter Credentials:** Username + password from `ADMIN_USERS_JSON`
3. **Session Created:** Browser gets `admin_session` cookie
4. **Dashboard Loaded:** All subsequent calls use session cookie
5. **Logout:** Session cookie deleted, redirected to login

### Understanding KPI Cards

| KPI | Definition | Example |
|---|---|---|
| **Total Messages** | All incoming messages (WhatsApp + Telegram + Website) | 1,234 |
| **Hot Leads (24h)** | Leads scored as "Hot" in last 24 hours | 45 |
| **Counsellor Assignments** | Leads assigned to counsellors today | 38 |
| **Response Time (avg)** | Average time from message to reply | 3.2 sec |
| **Session Uptime** | Time backend has been running | 48h 23m |
| **Channel Split** | Pie chart of message sources | 60% WhatsApp, 30% Telegram, 10% Website |

### Reading the Workflow Matrix

Shows all n8n workflows with:

- **Workflow Name** — Name from n8n
- **Recommended** — ✓ = should be enabled, ✗ = should be disabled
- **Current Status** — ✓ = enabled, ✗ = disabled
- **Executions (24h)** — Success | Failure counts
- **Last Execution** — When workflow last ran

**Example:**
| Workflow | Recommended | Status | Success | Failure | Last Run |
|---|---|---|---|---|---|
| 03-48hr-followup | ✓ | ✓ | 12 | 1 | 2h ago |
| 04-daily-hod-report | ✓ | ✓ | 1 | 0 | 23h ago |
| 01-main-bot | ✗ | ✗ | — | — | Disabled |

### Viewing Live Charts

#### 24h Lead Trend Chart
- **X-axis:** Hour of day (00:00 to 23:00)
- **Y-axis:** Message count
- **Shows:** Hourly volume of incoming messages
- **Use:** Identify peak hours, plan counsellor shifts

#### Counsellor Performance Chart
- **X-axis:** Counsellor name
- **Y-axis:** Assignments (orange) vs Conversions (blue)
- **Shows:** Work distribution and performance
- **Use:** Identify high performers, rebalance load

### Role-Based Permissions

#### Admin Role
- View all metrics
- See integration status
- Monitor workflow health
- Access full API via `auth/me` endpoint

#### Viewer Role
- View all metrics (read-only)
- Cannot modify settings
- Cannot access integration configuration
- Can see same dashboard as admin

**To restrict viewer access**, future version can add:
- Hidden admin-only controls
- Policy enforcement on API level

### Integration Health Panel

Shows real-time status of connected services:

| Service | Status | Meaning |
|---|---|---|
| **Groq API** | 🟢 Connected | AI responses working |
| **Groq API** | 🔴 Failed | Check GROQ_API_KEY and network |
| **WhatsApp** | 🟢 Configured | Ready to receive messages |
| **WhatsApp** | ⚫ Unconfigured | No WHATSAPP_*_TOKEN set |
| **Telegram** | 🟢 Configured | Ready for Telegram messages |
| **n8n** | 🟢 Connected | Live workflow polling active |
| **n8n** | 🔴 Disconnected | Check N8N_API_URL and N8N_API_KEY |
| **Google Sheets** | 🟢 Configured | Lead capture ready |
| **Google Sheets** | ⚫ Unconfigured | No GOOGLE_SHEETS_ID set |

---

## Troubleshooting

### Problem: Cannot Access `/admin`

**Symptoms:** Page returns 404 or blank page

**Solution:**
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check FastAPI loaded correctly:
   ```bash
   uvicorn backend.app:app --reload
   ```
3. Ensure no errors in terminal output

### Problem: Login Fails with "Invalid Credentials"

**Symptoms:** Username/password rejected even though credentials are correct

**Solution:**
1. Check `.env` has `ADMIN_USERS_JSON` set correctly
2. Verify JSON is valid (use [jsonlint.com](https://jsonlint.com))
3. Ensure no trailing commas in JSON
4. Restart backend server:
   ```bash
   # Stop with Ctrl+C and restart
   uvicorn backend.app:app --reload
   ```

**Example valid JSON:**
```json
[
  {"username":"admin","password":"Pass123","role":"admin"},
  {"username":"viewer","password":"Pass456","role":"viewer"}
]
```

### Problem: Dashboard Loads but Shows No Data

**Symptoms:** KPI cards show 0, charts are empty

**Solution:**
1. Backend is running but no messages have been processed yet
2. Expected behavior on fresh install
3. Send a test message via WhatsApp/Telegram to generate metrics
4. After processing 1+ messages, metrics appear

### Problem: n8n Shows "Disconnected"

**Symptoms:** Integration health shows n8n as 🔴 disconnected

**Solution:**
1. Verify n8n is running:
   ```bash
   curl http://localhost:5678/health
   ```
2. Check n8n API key is correct:
   ```bash
   curl -H "Authorization: Bearer YOUR_N8N_API_KEY" \
     http://localhost:5678/api/v1/user
   ```
3. Verify `.env` has correct `N8N_API_URL` and `N8N_API_KEY`
4. Restart backend to reconnect:
   ```bash
   # Ctrl+C to stop, then restart
   uvicorn backend.app:app --reload
   ```

### Problem: Session Cookie Not Persisting

**Symptoms:** Logged out after page refresh

**Solution:**
1. In development, set in [backend/app.py](backend/app.py):
   ```python
   "secure": False  # Allow HTTP cookies in dev
   ```
2. In production, ensure HTTPS enabled and:
   ```python
   "secure": True   # HTTPS-only
   ```
3. Check browser allows third-party cookies (some browser privacy modes block them)

### Problem: "Groq API is not configured" on Dashboard

**Symptoms:** Groq integration shows as unavailable

**Solution:**
1. Verify `GROQ_API_KEY` is set in `.env`
2. Check key format: should start with `gsk_`
3. Restart backend server
4. Test Groq connection:
   ```bash
   curl -X GET https://api.groq.com/openai/v1/models \
     -H "Authorization: Bearer gsk_YOUR_KEY"
   ```

### Problem: Charts Not Loading

**Symptoms:** "24h Lead Trend" and "Counsellor Performance" sections show loading spinner forever

**Solution:**
1. Check browser console for JavaScript errors (F12 → Console tab)
2. Verify API endpoint is responding:
   ```bash
   curl http://localhost:8000/api/admin/overview
   ```
3. Ensure Chart.js is loading (check network tab in DevTools)
4. Try clearing browser cache: Ctrl+Shift+Delete

### Problem: "ADMIN_SESSION_SECRET is required"

**Symptoms:** Backend fails to start with this error

**Solution:**
1. Add to `.env`:
   ```env
   ADMIN_SESSION_SECRET=your_random_32_char_string
   ```
2. Generate strong secret:
   ```bash
   # Windows PowerShell
   [System.Convert]::ToBase64String((1..32 | ForEach-Object { [byte](Get-Random -Maximum 256) }))
   
   # macOS/Linux
   openssl rand -base64 32
   ```
3. Restart backend

---

## API Reference

### Authentication Endpoints

#### Login
```
POST /api/admin/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "SecureAdminPass123"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "username": "admin",
    "role": "admin"
  }
}
```

Sets `admin_session` cookie automatically.

#### Get Current User
```
GET /api/admin/auth/me
```

**Response (200 OK):**
```json
{
  "username": "admin",
  "role": "admin"
}
```

**Response (401 Unauthorized):**
```json
{
  "error": "Not authenticated"
}
```

#### Logout
```
POST /api/admin/auth/logout
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

Clears `admin_session` cookie.

### Dashboard API

#### Get Admin Overview
```
GET /api/admin/overview
```

**Headers:** (Choose one)
- Session cookie: `Cookie: admin_session=...`
- OR Bearer token: `Authorization: Bearer your_api_secret_key`

**Response (200 OK):**
```json
{
  "provider_status": {
    "provider": "groq",
    "model": "mixtral-8x7b-32768",
    "status": "active"
  },
  "integrations": {
    "whatsapp": {
      "status": "configured",
      "phone_id": "116502...***"
    },
    "telegram": {
      "status": "configured",
      "bot_name": "IIST_AdmitBot"
    },
    "google_sheets": {
      "status": "unconfigured"
    },
    "n8n": {
      "status": "connected",
      "url": "http://localhost:5678",
      "total_workflows": 8,
      "active_workflows": 6
    },
    "tawk_to": {
      "status": "unconfigured"
    }
  },
  "workflows": [
    {
      "id": "workflow_1",
      "name": "01-main-bot",
      "recommended": false,
      "status": "disabled",
      "success_24h": 0,
      "failure_24h": 0,
      "last_execution": null
    },
    {
      "id": "workflow_3",
      "name": "03-48hr-followup",
      "recommended": true,
      "status": "enabled",
      "success_24h": 12,
      "failure_24h": 1,
      "last_execution": "2026-03-31T14:22:30Z"
    }
  ],
  "kpis": {
    "total_messages": 1234,
    "hot_leads_24h": 45,
    "counsellor_assignments_24h": 38,
    "avg_response_time_ms": 3200,
    "session_uptime_hours": 48.38,
    "channel_distribution": {
      "whatsapp": 0.60,
      "telegram": 0.30,
      "website": 0.10
    }
  },
  "analytics": {
    "hourly_messages": {
      "00": 12,
      "01": 8,
      "02": 5,
      ...
      "23": 15
    },
    "counsellor_performance": {
      "Ritu Sharma": {"assignments": 12, "conversions": 8},
      "Priya Verma": {"assignments": 10, "conversions": 7},
      ...
    }
  }
}
```

---

## Next Steps

After setups complete:

1. **Configure n8n Workflows**
   - Import JSON files from `n8n-workflows/` folder
   - Enable Phase 3+ workflows (03, 04, 05, 06, 07, 08)
   - Keep 01-main-bot and 02-hot-lead-alert disabled (backend handles these)

2. **Set Up WhatsApp & Telegram Webhooks**
   - Register Meta WhatsApp Business API webhook: `https://your-domain/webhook/whatsapp`
   - Register Telegram webhook: `https://your-domain/webhook/telegram/{TELEGRAM_WEBHOOK_SECRET}`

3. **Monitor Live Metrics**
   - Access admin dashboard at `https://your-domain/admin`
   - Invite counsellors as `viewer` role
   - Invite principal as `viewer` role

4. **Future Enhancements**
   - Add bcrypt password hashing (currently plaintext)
   - Add strict role-based API endpoint access
   - Add workflow execution retry/restart buttons
   - Add counsellor real-time chat monitoring
   - Integrate Looker Studio BI dashboards with backend metrics

---

*For questions or issues, refer to main [README.md](README.md) or check troubleshooting section above.*
