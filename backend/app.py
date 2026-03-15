"""
IIST AdmitBot — Main FastAPI Application
Handles:
  - WhatsApp Business API webhook (GET verification + POST messages)
  - Tawk.to website chat widget webhook
  - Health check endpoint
"""

import logging
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.chatbot.ai_client import AIResponse, generate_response
from backend.chatbot.knowledge_base import get_system_prompt
from backend.chatbot.language_detector import detect_language
from backend.chatbot.lead_scorer import score_lead
from backend.config import settings
from backend.integrations.google_sheets import append_interaction, append_lead
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
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
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


@app.get("/health")
async def health_check():
    """Health check endpoint — used by UptimeRobot to prevent Railway sleep."""
    return {"status": "ok", "service": "IIST AdmitBot", "timestamp": time.time()}


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
    Receive incoming WhatsApp messages, process via Gemini AI,
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
    2. Build Gemini prompt with knowledge base
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

    # Step 1: Language detection (for logging / analytics)
    language = detect_language(message_text)
    logger.debug("Detected language: %s", language)

    # Look up per-user session context (applies to WhatsApp, Telegram, Tawk.to)
    if not conversation_context:
        conversation_context = _sessions.get(phone_number, "")

    # Step 2: Build Gemini prompt
    prompt = get_system_prompt(
        student_message=message_text,
        conversation_context=conversation_context,
        preferred_language=language.value,
    )

    # Step 3: Get AI response
    try:
        ai_response = await generate_response(prompt)
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
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
        logger.info("Hot lead alert sent to counsellor %s", counsellor)

    # Step 8: Escalation
    if ai_response.needs_escalation and source_channel == "WhatsApp":
        await send_escalation_message(phone_number)

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
        ai_response = AIResponse(
            reply_text=(
                "I'm having a brief issue right now. 🙏 "
                "Please contact us: admissions@iist.ac.in"
            ),
            needs_escalation=True,
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
    phone_number = req.phone or f"web_{session_id[:8]}"
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
        except Exception as exc:
            logger.warning("Counsellor alert failed in /api/chat: %s", exc)

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
    if settings.api_secret_key:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {settings.api_secret_key}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    from backend.integrations.google_sheets import get_daily_summary
    summary = get_daily_summary()
    return {"status": "ok", "summary": summary}

