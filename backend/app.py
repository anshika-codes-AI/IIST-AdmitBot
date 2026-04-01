"""
IIST AdmitBot — Main FastAPI Application
Handles:
  - WhatsApp Business API webhook (GET verification + POST messages)
  - Tawk.to website chat widget webhook
  - Health check endpoint
"""

import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from backend.chatbot.ai_client import AIResponse, generate_faq_fallback_response, generate_response
from backend.chatbot.knowledge_base import get_system_prompt
from backend.chatbot.language_detector import detect_language
from backend.chatbot.lead_scorer import score_lead
from backend.config import settings
from backend.integrations.google_sheets import (
    append_interaction,
    append_lead,
    get_admin_analytics_snapshot,
)
from backend.integrations.telegram import parse_webhook_update, send_telegram_message
from backend.integrations.whatsapp import (
    parse_webhook_payload,
    send_counsellor_alert,
    send_escalation_message,
    send_text_message,
)
from backend.workflows.counsellor_assignment import get_next_counsellor

# In-memory session store: session_id → conversation_context string
# Resets on server restart — acceptable for MVP (stateless channels like
# WhatsApp maintain context differently anyway).
_sessions: Dict[str, str] = {}
_runtime_metrics: Dict[str, Any] = {
    "messages_total": 0,
    "errors_total": 0,
    "escalations_total": 0,
    "hot_leads_total": 0,
    "channel_breakdown": {"WhatsApp": 0, "Telegram": 0, "Website": 0},
    "avg_response_ms": 0.0,
}
_hourly_events: list[Dict[str, Any]] = []
_phone_to_counsellor: Dict[str, str] = {}
_counsellor_stats: Dict[str, Dict[str, int]] = {}
_handoff_state: Dict[str, bool] = {}
_started_at = time.time()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IIST AdmitBot",
    description=(
        "24/7 AI-powered bilingual admission chatbot and lead management system "
        "for Indore Institute of Science & Technology."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_session_secret,
    session_cookie="iist_admin_session",
    same_site="lax",
    https_only=False,
)


# ---------------------------------------------------------------------------
# Pydantic models for the /api/chat REST endpoint (used by Lovable frontend)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    name: str = ""
    phone: str = ""


class ChatResponse(BaseModel):
    reply: str
    lead_score: str
    language: str
    needs_escalation: bool
    session_id: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


def _find_admin_user(username: str, password: str) -> Optional[Dict[str, str]]:
    for user in settings.admin_users:
        if user["username"] == username and user["password"] == password:
            return user
    return None


def _get_session_user(request: Request) -> Optional[Dict[str, str]]:
    username = request.session.get("admin_username")
    role = request.session.get("admin_role")
    if not username or not role:
        return None
    return {"username": username, "role": role}


def _require_admin_session(request: Request, allowed_roles: set[str] | None = None) -> Dict[str, str]:
    user = _get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if allowed_roles and user["role"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return user


def _maybe_bearer_override(request: Request) -> bool:
    """Backwards-compatible auth path for service integrations."""
    if not settings.api_secret_key:
        return False
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {settings.api_secret_key}"


@app.get("/health")
async def health_check():
    """Health check endpoint — used by UptimeRobot to prevent Railway sleep."""
    return {"status": "ok", "service": "IIST AdmitBot", "timestamp": time.time()}


def _record_hourly_event(
    phone_number: str,
    lead_score: str,
    needs_escalation: bool,
    conversion: bool,
) -> None:
    now = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0).isoformat()
    phone = (phone_number or "").strip()
    _hourly_events.append(
        {
            "ts": now.isoformat(),
            "hour": hour_start,
            "phone": phone,
            "hot": lead_score == "Hot",
            "escalated": needs_escalation,
            "conversion": conversion,
        }
    )
    # Keep last 72h in memory to support charts without unbounded growth.
    cutoff = now - timedelta(hours=72)
    _hourly_events[:] = [
        item for item in _hourly_events
        if datetime.fromisoformat(item["ts"]) >= cutoff
    ]


def _try_detect_conversion(message_text: str) -> bool:
    text = (message_text or "").lower()
    markers = [
        "admission done",
        "enrolled",
        "enrolment done",
        "seat confirmed",
        "fees paid",
        "joined iist",
    ]
    return any(marker in text for marker in markers)


def _extract_phone_number(text: str) -> str:
    """Extract a likely phone number (10 to 13 digits) from free text."""
    digits = re.sub(r"\D", "", text or "")
    if 10 <= len(digits) <= 13:
        return digits
    return ""


def _is_ack_message(text: str) -> bool:
    msg = (text or "").strip().lower()
    return msg in {
        "ok", "okay", "oky", "k", "thanks", "thank you", "thx", "done",
        "theek", "thik", "ठीक", "acha", "accha",
    }


def _looks_like_handoff_reply(reply_text: str) -> bool:
    text = (reply_text or "").lower()
    markers = [
        "counsellor",
        "admissions team",
        "call you",
        "contact you",
        "connect you",
    ]
    return any(marker in text for marker in markers)


def _is_informational_query(text: str) -> bool:
    msg = (text or "").lower()
    patterns = [
        r"\bfees?\b",
        r"\bhostel\b",
        r"\bscholarship\b",
        r"\bplacement\b",
        r"\beligib",
        r"\bjee\b",
        r"\bcutoff\b",
        r"\bdeadline\b",
        r"\bdocument",
        r"\badmission\s*process\b",
        r"\bcourse\b",
        r"\bbranch\b",
        r"\bcampus\b",
        r"\btiming\b",
        r"\bhow\b",
        r"\bwhat\b",
        r"\bwhen\b",
        r"\bkaise\b",
        r"\bkya\b",
        r"\bkitna\b",
    ]
    return any(re.search(pattern, msg) for pattern in patterns)


def _is_explicit_handoff_request(text: str) -> bool:
    msg = (text or "").lower()
    patterns = [
        r"\bcounsell?or\b",
        r"\bhuman\b",
        r"\bagent\b",
        r"\bcall\s*me\b",
        r"\bcontact\s*me\b",
        r"\bbaat\s*kar",
        r"\bphone\s*call\b",
    ]
    return any(re.search(pattern, msg) for pattern in patterns)


def _stabilize_ai_response(
    conversation_key: str,
    message_text: str,
    conversation_context: str,
    ai_response: AIResponse,
) -> AIResponse:
    """Reduce repetitive escalation loops and improve acknowledgement turns."""
    if not conversation_key:
        return ai_response

    phone_in_message = _extract_phone_number(message_text)
    phone_in_context = _extract_phone_number(conversation_context)
    already_in_handoff = _handoff_state.get(conversation_key, False)

    if phone_in_message:
        _handoff_state[conversation_key] = True
        already_in_handoff = True

    if _is_ack_message(message_text) and already_in_handoff:
        ai_response.reply_text = (
            "Thanks. Your details are shared with the admissions team and you should get a call shortly. "
            "Meanwhile, I can help with eligibility, scholarship, hostel, or documents."
        )
        ai_response.needs_escalation = False
        return ai_response

    # Guardrail: for regular admission FAQs, keep the conversation self-service
    # unless the student explicitly asks for a human handoff.
    if (
        ai_response.needs_escalation
        and _is_informational_query(message_text)
        and not _is_explicit_handoff_request(message_text)
    ):
        fallback = generate_faq_fallback_response(message_text)
        ai_response.reply_text = fallback.reply_text
        ai_response.needs_escalation = False
        if not ai_response.intent_score:
            ai_response.intent_score = fallback.intent_score
        return ai_response

    if (
        ai_response.needs_escalation
        and _looks_like_handoff_reply(ai_response.reply_text)
        and (phone_in_message or phone_in_context)
    ):
        ai_response.reply_text = (
            "Thanks, I have your number. Our admissions team will call you shortly with exact details. "
            "Until then, I can also share eligibility, scholarship, hostel, and document guidance."
        )
        if already_in_handoff:
            ai_response.needs_escalation = False
        _handoff_state[conversation_key] = True

    if ai_response.needs_escalation:
        _handoff_state[conversation_key] = True

    return ai_response


def _build_hourly_trend(hours: int = 24) -> Dict[str, list[Any]]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    buckets: Dict[str, Dict[str, int]] = {}
    labels: list[str] = []
    for i in range(hours - 1, -1, -1):
        key_dt = now - timedelta(hours=i)
        key = key_dt.isoformat()
        buckets[key] = {"messages": 0, "hot": 0, "conversions": 0}
        labels.append(key_dt.strftime("%H:%M"))

    for item in _hourly_events:
        hour_key = item.get("hour")
        if hour_key not in buckets:
            continue
        buckets[hour_key]["messages"] += 1
        if item.get("hot"):
            buckets[hour_key]["hot"] += 1
        if item.get("conversion"):
            buckets[hour_key]["conversions"] += 1

    ordered_keys = list(buckets.keys())
    return {
        "labels": labels,
        "messages": [buckets[k]["messages"] for k in ordered_keys],
        "hot_leads": [buckets[k]["hot"] for k in ordered_keys],
        "conversions": [buckets[k]["conversions"] for k in ordered_keys],
    }


async def _fetch_n8n_runtime_status() -> Dict[str, Any]:
    if not settings.n8n_api_url or not settings.n8n_api_key:
        return {
            "connected": False,
            "reason": "n8n_api_not_configured",
            "workflows": [],
            "summary": {"active": 0, "inactive": 0, "success_24h": 0, "failed_24h": 0},
        }

    base = settings.n8n_api_url.rstrip("/")
    headers = {"X-N8N-API-KEY": settings.n8n_api_key}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            wf_resp = await client.get(f"{base}/api/v1/workflows", headers=headers)
            ex_resp = await client.get(
                f"{base}/api/v1/executions?limit=100",
                headers=headers,
            )

        wf_resp.raise_for_status()
        ex_resp.raise_for_status()
        workflows_payload = wf_resp.json()
        executions_payload = ex_resp.json()

        raw_workflows = workflows_payload.get("data", workflows_payload)
        raw_executions = executions_payload.get("data", executions_payload)
        if not isinstance(raw_workflows, list):
            raw_workflows = []
        if not isinstance(raw_executions, list):
            raw_executions = []

        by_workflow: Dict[str, Dict[str, int]] = {}
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        success_24h = 0
        failed_24h = 0

        for ex in raw_executions:
            wf_id = str(ex.get("workflowId") or ex.get("workflow_id") or "")
            if wf_id not in by_workflow:
                by_workflow[wf_id] = {"success": 0, "failed": 0}
            status_text = str(ex.get("status") or "").lower()
            finished = str(ex.get("finished") or "")
            started_raw = ex.get("startedAt") or ex.get("started_at")
            started_dt = None
            if started_raw:
                try:
                    started_dt = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
                except Exception:
                    started_dt = None
            in_window = started_dt >= since if started_dt else True
            ok = status_text in {"success", "succeeded"} or finished in {True, "true"}
            failed = status_text in {"error", "failed", "crashed"}
            if ok:
                by_workflow[wf_id]["success"] += 1
                if in_window:
                    success_24h += 1
            if failed:
                by_workflow[wf_id]["failed"] += 1
                if in_window:
                    failed_24h += 1

        output_workflows = []
        active = 0
        inactive = 0
        for wf in raw_workflows:
            wf_id = str(wf.get("id") or "")
            is_active = bool(wf.get("active") is True)
            if is_active:
                active += 1
            else:
                inactive += 1
            counters = by_workflow.get(wf_id, {"success": 0, "failed": 0})
            output_workflows.append(
                {
                    "id": wf_id,
                    "name": wf.get("name") or wf_id,
                    "active": is_active,
                    "success_24h": counters["success"],
                    "failed_24h": counters["failed"],
                }
            )

        return {
            "connected": True,
            "workflows": output_workflows,
            "summary": {
                "active": active,
                "inactive": inactive,
                "success_24h": success_24h,
                "failed_24h": failed_24h,
            },
        }
    except Exception as exc:
        logger.warning("n8n status polling failed: %s", exc)
        return {
            "connected": False,
            "reason": "n8n_poll_failed",
            "detail": str(exc),
            "workflows": [],
            "summary": {"active": 0, "inactive": 0, "success_24h": 0, "failed_24h": 0},
        }


def _config_present(value: str) -> bool:
    return bool(str(value or "").strip())


def _workflow_catalog() -> list[Dict[str, str]]:
    return [
        {
            "id": "01-main-bot",
            "file": "n8n-workflows/01-main-bot.json",
            "category": "legacy-realtime",
            "recommended_state": "disabled",
        },
        {
            "id": "02-hot-lead-alert",
            "file": "n8n-workflows/02-hot-lead-alert.json",
            "category": "legacy-alert",
            "recommended_state": "disabled",
        },
        {
            "id": "03-48hr-followup",
            "file": "n8n-workflows/03-48hr-followup.json",
            "category": "nurture",
            "recommended_state": "enabled",
        },
        {
            "id": "04-daily-hod-report",
            "file": "n8n-workflows/04-daily-hod-report.json",
            "category": "reporting",
            "recommended_state": "enabled",
        },
        {
            "id": "05-weekly-principal-report",
            "file": "n8n-workflows/05-weekly-principal-report.json",
            "category": "reporting",
            "recommended_state": "enabled",
        },
        {
            "id": "06-deadline-reminder",
            "file": "n8n-workflows/06-deadline-reminder.json",
            "category": "campaign",
            "recommended_state": "enabled",
        },
        {
            "id": "07-counsellor-assignment",
            "file": "n8n-workflows/07-counsellor-assignment.json",
            "category": "optional-ops",
            "recommended_state": "enabled",
        },
        {
            "id": "08-enrolment-trigger",
            "file": "n8n-workflows/08-enrolment-trigger.json",
            "category": "post-conversion",
            "recommended_state": "enabled",
        },
    ]


def _workflow_states() -> list[Dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    workflows: list[Dict[str, Any]] = []
    for item in _workflow_catalog():
        exists = (root / item["file"]).exists()
        workflows.append({**item, "file_exists": exists})
    return workflows


@app.get("/admin")
async def admin_dashboard() -> FileResponse:
    """Serve the admin dashboard frontend."""
    dashboard_path = Path(__file__).resolve().parents[1] / "website" / "admin-dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Admin dashboard not found")
    return FileResponse(dashboard_path)


@app.post("/api/admin/auth/login")
async def admin_login(request: Request, payload: AdminLoginRequest):
    user = _find_admin_user(payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session["admin_username"] = user["username"]
    request.session["admin_role"] = user["role"]
    return {
        "status": "ok",
        "user": {"username": user["username"], "role": user["role"]},
    }


@app.post("/api/admin/auth/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.get("/api/admin/auth/me")
async def admin_me(request: Request):
    user = _get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"status": "ok", "user": user}


@app.get("/api/admin/overview")
async def api_admin_overview(request: Request):
    """Operational status for the admin dashboard."""
    user = _get_session_user(request)
    if not user and not _maybe_bearer_override(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    if user and user["role"] not in {"admin", "viewer"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    runtime_seconds = int(time.time() - _started_at)
    total = _runtime_metrics["messages_total"]
    escalations = _runtime_metrics["escalations_total"]
    hot_leads = _runtime_metrics["hot_leads_total"]
    escalation_rate = round((escalations / total) * 100, 2) if total else 0.0
    hot_lead_rate = round((hot_leads / total) * 100, 2) if total else 0.0
    n8n_runtime = await _fetch_n8n_runtime_status()
    trend_24h = _build_hourly_trend(hours=24)
    runtime_counsellor_performance = [
        {
            "counsellor": name,
            "assigned": vals.get("assigned", 0),
            "conversions": vals.get("conversions", 0),
            "conversion_rate": round(
                (vals.get("conversions", 0) / vals.get("assigned", 1)) * 100, 2
            ) if vals.get("assigned", 0) else 0.0,
        }
        for name, vals in _counsellor_stats.items()
    ]
    runtime_counsellor_performance.sort(key=lambda item: item["assigned"], reverse=True)

    sheets_analytics = get_admin_analytics_snapshot(recent_limit=25)
    counsellor_for_dashboard = (
        sheets_analytics["counsellor_performance"]
        if sheets_analytics.get("counsellor_performance")
        else runtime_counsellor_performance
    )

    return {
        "status": "ok",
        "auth": {
            "username": user["username"] if user else "service-token",
            "role": user["role"] if user else "service",
        },
        "ai_provider": {
            "mode": "groq-only",
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "configured": _config_present(settings.groq_api_key),
        },
        "integrations": {
            "whatsapp": _config_present(settings.whatsapp_access_token)
            and _config_present(settings.whatsapp_phone_number_id),
            "telegram": _config_present(settings.telegram_bot_token),
            "google_sheets": _config_present(settings.google_sheets_id),
            "n8n": _config_present(settings.n8n_webhook_url),
            "tawkto": _config_present(settings.tawkto_api_key),
        },
        "runtime": {
            "uptime_seconds": runtime_seconds,
            "messages_total": total,
            "errors_total": _runtime_metrics["errors_total"],
            "avg_response_ms": round(_runtime_metrics["avg_response_ms"], 2),
            "hot_lead_rate_percent": hot_lead_rate,
            "escalation_rate_percent": escalation_rate,
            "channel_breakdown": _runtime_metrics["channel_breakdown"],
            "active_sessions": len(_sessions),
        },
        "analytics": {
            "hourly_trend_24h": trend_24h,
            "counsellor_conversion": counsellor_for_dashboard,
            "source_roi": sheets_analytics.get("source_roi", []),
            "regional_heat": sheets_analytics.get("regional_heat", []),
            "recent_enquiries": sheets_analytics.get("recent_enquiries", []),
            "persistent_totals": sheets_analytics.get("totals", {}),
        },
        "n8n_runtime": n8n_runtime,
        "workflows": _workflow_states(),
    }


# ---------------------------------------------------------------------------
# WhatsApp Webhook
# ---------------------------------------------------------------------------

@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """
    Meta webhook verification handshake.
    Meta sends a GET request with a challenge string — we must echo it back
    if our verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning(
        "WhatsApp webhook verification failed — token mismatch or wrong mode"
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receive incoming WhatsApp messages, process via Groq AI,
    capture lead to Google Sheets, and send reply.
    """
    payload: Dict[str, Any] = await request.json()
    messages = parse_webhook_payload(payload)

    for msg in messages:
        await _process_message(
            phone_number=msg.phone_number,
            message_text=msg.message_text,
            student_name=msg.name,
            source_channel="WhatsApp",
        )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Telegram Webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """
    Receive incoming Telegram bot updates.
    Configure Telegram webhook URL to include TELEGRAM_WEBHOOK_SECRET, e.g.
    /webhook/telegram/<secret> to prevent random public posts.
    """
    if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    payload: Dict[str, Any] = await request.json()
    messages = parse_webhook_update(payload)

    for msg in messages:
        result = await _process_message(
            phone_number=f"tg_{msg.chat_id}",
            message_text=msg.message_text,
            student_name=msg.name,
            source_channel="Telegram",
        )
        await send_telegram_message(msg.chat_id, result["reply"])

        if result["needs_escalation"]:
            await send_telegram_message(
                msg.chat_id,
                "I am connecting you to our admissions counsellor. "
                "Please share your phone number for a callback.",
            )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tawk.to Website Widget Webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/tawkto")
async def tawkto_webhook(request: Request):
    """
    Receive incoming messages from Tawk.to website chat widget.
    Processes them through the same pipeline as WhatsApp messages.
    """
    payload: Dict[str, Any] = await request.json()

    # Tawk.to webhook payload format
    event = payload.get("event", "")
    if event != "chat:start" and event != "chat:message":
        return {"status": "ignored", "event": event}

    visitor = payload.get("visitor", {})
    message_text = payload.get("message", {}).get("text", "")
    phone_number = visitor.get("phone", "website_visitor")
    student_name = visitor.get("name", "")

    if not message_text:
        return {"status": "ok", "note": "empty message"}

    await _process_message(
        phone_number=phone_number,
        message_text=message_text,
        student_name=student_name,
        source_channel="Website",
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Core message processing pipeline
# ---------------------------------------------------------------------------

async def _process_message(
    phone_number: str,
    message_text: str,
    student_name: str = "",
    source_channel: str = "WhatsApp",
    conversation_context: str = "",
) -> Dict[str, Any]:
    """
    Core pipeline:
    1. Detect language
    2. Build AI prompt with knowledge base
    3. Get AI response + structured data
    4. Score lead
    5. Capture to Google Sheets
    6. Send reply to student
    7. Alert counsellor if Hot lead
    8. Escalate if needed
    """
    logger.info(
        "Processing message from %s via %s: %.60s",
        phone_number,
        source_channel,
        message_text,
    )
    started = time.time()

    # Step 1: Language detection (for logging / analytics)
    language = detect_language(message_text)
    logger.debug("Detected language: %s", language)

    # Look up per-user session context (applies to WhatsApp, Telegram, Tawk.to)
    if not conversation_context:
        conversation_context = _sessions.get(phone_number, "")

    # Step 2: Build AI prompt
    prompt = get_system_prompt(
        student_message=message_text,
        conversation_context=conversation_context,
        preferred_language=language.value,
    )

    # Step 3: Get AI response
    try:
        ai_response = await generate_response(prompt)
    except Exception as exc:
        logger.error("AI provider call failed: %s", exc)
        _runtime_metrics["errors_total"] += 1
        fallback_text = "I'm having a brief issue. Please contact us at admissions@indoreinstitute.com"
        if source_channel == "WhatsApp":
            await send_text_message(phone_number, fallback_text)
        elif source_channel == "Telegram":
            await send_telegram_message(phone_number.replace("tg_", ""), fallback_text)
        return {
            "reply": fallback_text,
            "lead_score": "Cold",
            "needs_escalation": True,
        }

    handoff_already_started = _handoff_state.get(phone_number, False)
    ai_response = _stabilize_ai_response(
        conversation_key=phone_number,
        message_text=message_text,
        conversation_context=conversation_context,
        ai_response=ai_response,
    )

    # Update per-user session memory so next turn has conversation context
    _sessions[phone_number] = (
        conversation_context + f"\nStudent: {message_text}\nBot: {ai_response.reply_text}"
    ).strip()

    # Step 4: Score lead
    extracted = ai_response.extracted_data
    lead_score = score_lead(
        message=message_text,
        ai_score=ai_response.intent_score,
        has_phone=bool(extracted.get("phone") or (phone_number and not phone_number.startswith("website"))),
        has_name=bool(extracted.get("name") or student_name),
        has_score=bool(extracted.get("jee_percentile")),
    )

    # Merge name from conversation or extracted data
    final_name = student_name or extracted.get("name") or ""

    # Step 5: Capture lead to Google Sheets
    lead_id = phone_number.lstrip("+").replace(" ", "") or str(uuid.uuid4())[:8]
    try:
        append_lead(
            lead_id=lead_id,
            phone_number=phone_number,
            student_name=final_name,
            city=extracted.get("city") or "",
            course_interest=extracted.get("course_interest") or "",
            jee_score=extracted.get("jee_percentile") or "",
            source_channel=source_channel,
            lead_score=lead_score.value,
            conversation_history=f"Student: {message_text}\nBot: {ai_response.reply_text}",
        )
    except Exception as exc:
        logger.warning("Google Sheets unavailable — lead not saved: %s", exc)

    # Step 5b: Log interaction to Interactions sheet (analytics / QA)
    try:
        append_interaction(
            interaction_id=str(uuid.uuid4())[:8],
            lead_id=lead_id,
            source_channel=source_channel,
            student_name=final_name,
            phone_number=phone_number,
            student_message=message_text,
            bot_reply=ai_response.reply_text,
            query_category="other",
            intent_score=ai_response.intent_score or "Cold",
            lead_score=lead_score.value,
            needs_escalation=ai_response.needs_escalation,
            bot_resolved=not ai_response.needs_escalation,
            language=language.value,
            response_time_ms=0,
        )
    except Exception as exc:
        logger.warning("Interaction log failed: %s", exc)

    # Step 6: Send reply to student (WhatsApp channel only)
    if source_channel == "WhatsApp" and phone_number:
        await send_text_message(phone_number, ai_response.reply_text)

    # Step 7: Hot lead — alert counsellor
    if lead_score.value == "Hot" and settings.counsellor_list:
        counsellor = get_next_counsellor(settings.counsellor_list)
        await send_counsellor_alert(
            counsellor_number=counsellor,
            student_name=final_name,
            student_phone=phone_number,
            city=extracted.get("city") or "",
            course_interest=extracted.get("course_interest") or "",
            lead_score=lead_score.value,
        )
        _phone_to_counsellor[phone_number] = counsellor
        stats = _counsellor_stats.setdefault(counsellor, {"assigned": 0, "conversions": 0})
        stats["assigned"] += 1
        logger.info("Hot lead alert sent to counsellor %s", counsellor)

    # Step 8: Escalation
    if ai_response.needs_escalation and source_channel == "WhatsApp" and not handoff_already_started:
        await send_escalation_message(phone_number)

    conversion_detected = _try_detect_conversion(message_text)
    if conversion_detected:
        counsellor = _phone_to_counsellor.get(phone_number)
        if counsellor:
            stats = _counsellor_stats.setdefault(counsellor, {"assigned": 0, "conversions": 0})
            stats["conversions"] += 1

    elapsed_ms = max((time.time() - started) * 1000, 0.0)
    _runtime_metrics["messages_total"] += 1
    _runtime_metrics["channel_breakdown"][source_channel] = (
        _runtime_metrics["channel_breakdown"].get(source_channel, 0) + 1
    )
    if ai_response.needs_escalation:
        _runtime_metrics["escalations_total"] += 1
    if lead_score.value == "Hot":
        _runtime_metrics["hot_leads_total"] += 1
    count = _runtime_metrics["messages_total"]
    avg = _runtime_metrics["avg_response_ms"]
    _runtime_metrics["avg_response_ms"] = ((avg * (count - 1)) + elapsed_ms) / count
    _record_hourly_event(
        phone_number=phone_number,
        lead_score=lead_score.value,
        needs_escalation=ai_response.needs_escalation,
        conversion=conversion_detected,
    )

    return {
        "reply": ai_response.reply_text,
        "lead_score": lead_score.value,
        "needs_escalation": ai_response.needs_escalation,
    }


# ---------------------------------------------------------------------------
# REST API for Lovable frontend (and any future web client)
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    """
    Stateful chat endpoint for the Lovable frontend and website widget.
    Maintains per-session conversation context in memory.

    Body:
        message     — student's message text (required)
        session_id  — resume an existing conversation (optional, auto-generated if blank)
        name        — student's name if known (optional)
        phone       — student's phone number (optional)

    Returns:
        reply, lead_score, language, needs_escalation, session_id
    """
    started = time.time()
    session_id = req.session_id.strip() or str(uuid.uuid4())
    conversation_context = _sessions.get(session_id, "")

    language = detect_language(req.message)
    prompt = get_system_prompt(
        student_message=req.message,
        conversation_context=conversation_context,
        preferred_language=language.value,
    )

    try:
        ai_response = await generate_response(prompt)
    except Exception as exc:
        logger.error("AI call failed in /api/chat: %s", exc)
        _runtime_metrics["errors_total"] += 1
        ai_response = AIResponse(
            reply_text=(
                "I'm having a brief issue right now. 🙏 "
                "Please contact us: admissions@iist.ac.in"
            ),
            needs_escalation=True,
        )

    ai_response = _stabilize_ai_response(
        conversation_key=session_id,
        message_text=req.message,
        conversation_context=conversation_context,
        ai_response=ai_response,
    )

    extracted = ai_response.extracted_data
    lead_score = score_lead(
        message=req.message,
        ai_score=ai_response.intent_score,
        has_phone=bool(extracted.get("phone") or req.phone),
        has_name=bool(extracted.get("name") or req.name),
        has_score=bool(extracted.get("jee_percentile")),
    )

    # Persist conversation turn in session store
    _sessions[session_id] = (
        conversation_context
        + f"\nStudent: {req.message}\nBot: {ai_response.reply_text}"
    ).strip()

    # Async lead capture (fire-and-forget style — never block the chat response)
    extracted_phone = _extract_phone_number(req.message)
    phone_number = req.phone or extracted.get("phone") or extracted_phone or f"web_{session_id[:8]}"
    final_name = req.name or extracted.get("name") or ""
    lead_id = phone_number.lstrip("+").replace(" ", "")
    try:
        append_lead(
            lead_id=lead_id,
            phone_number=phone_number,
            student_name=final_name,
            city=extracted.get("city") or "",
            course_interest=extracted.get("course_interest") or "",
            jee_score=extracted.get("jee_percentile") or "",
            source_channel="Website",
            lead_score=lead_score.value,
            conversation_history=_sessions[session_id],
        )
    except Exception as exc:
        logger.warning("Google Sheets unavailable in /api/chat: %s", exc)

    # Hot lead counsellor alert
    if lead_score.value == "Hot" and settings.counsellor_list:
        try:
            counsellor = get_next_counsellor(settings.counsellor_list)
            await send_counsellor_alert(
                counsellor_number=counsellor,
                student_name=final_name,
                student_phone=phone_number,
                city=extracted.get("city") or "",
                course_interest=extracted.get("course_interest") or "",
                lead_score=lead_score.value,
            )
            _phone_to_counsellor[phone_number] = counsellor
            stats = _counsellor_stats.setdefault(counsellor, {"assigned": 0, "conversions": 0})
            stats["assigned"] += 1
        except Exception as exc:
            logger.warning("Counsellor alert failed in /api/chat: %s", exc)

    conversion_detected = _try_detect_conversion(req.message)
    if conversion_detected:
        counsellor = _phone_to_counsellor.get(phone_number)
        if counsellor:
            stats = _counsellor_stats.setdefault(counsellor, {"assigned": 0, "conversions": 0})
            stats["conversions"] += 1

    elapsed_ms = max((time.time() - started) * 1000, 0.0)
    _runtime_metrics["messages_total"] += 1
    _runtime_metrics["channel_breakdown"]["Website"] = (
        _runtime_metrics["channel_breakdown"].get("Website", 0) + 1
    )
    if ai_response.needs_escalation:
        _runtime_metrics["escalations_total"] += 1
    if lead_score.value == "Hot":
        _runtime_metrics["hot_leads_total"] += 1
    count = _runtime_metrics["messages_total"]
    avg = _runtime_metrics["avg_response_ms"]
    _runtime_metrics["avg_response_ms"] = ((avg * (count - 1)) + elapsed_ms) / count
    _record_hourly_event(
        phone_number=phone_number,
        lead_score=lead_score.value,
        needs_escalation=ai_response.needs_escalation,
        conversion=conversion_detected,
    )

    return ChatResponse(
        reply=ai_response.reply_text,
        lead_score=lead_score.value,
        language=language.value,
        needs_escalation=ai_response.needs_escalation,
        session_id=session_id,
    )


@app.get("/api/leads")
async def api_leads(request: Request):
    """
    Return today's lead summary for the Lovable dashboard.
    Protected by a simple bearer token (set API_SECRET_KEY in .env).
    """
    user = _get_session_user(request)
    if user:
        if user["role"] not in {"admin", "viewer"}:
            raise HTTPException(status_code=403, detail="Insufficient role")
    elif not _maybe_bearer_override(request):
        raise HTTPException(status_code=401, detail="Authentication required")

    from backend.integrations.google_sheets import get_daily_summary
    summary = get_daily_summary()
    return {"status": "ok", "summary": summary}

