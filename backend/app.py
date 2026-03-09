"""
IIST AdmitBot — Main FastAPI Application
Handles:
  - WhatsApp Business API webhook (GET verification + POST messages)
  - Tawk.to website chat widget webhook
  - Health check endpoint
"""

import logging
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.chatbot.gemini_client import generate_response
from backend.chatbot.knowledge_base import get_system_prompt
from backend.chatbot.language_detector import detect_language
from backend.chatbot.lead_scorer import score_lead
from backend.config import settings
from backend.integrations.google_sheets import append_lead
from backend.integrations.whatsapp import (
    parse_webhook_payload,
    send_counsellor_alert,
    send_escalation_message,
    send_text_message,
)
from backend.workflows.counsellor_assignment import get_next_counsellor

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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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
) -> None:
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

    # Step 2: Build Gemini prompt
    prompt = get_system_prompt(
        student_message=message_text,
        conversation_context=conversation_context,
    )

    # Step 3: Get AI response
    try:
        ai_response = await generate_response(prompt)
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        await send_text_message(
            phone_number,
            "I'm having a brief issue. 🙏 Please contact us at admissions@iist.ac.in",
        )
        return

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
    append_lead(
        phone_number=phone_number,
        student_name=final_name,
        city=extracted.get("city") or "",
        course_interest=extracted.get("course_interest") or "",
        jee_score=extracted.get("jee_percentile") or "",
        source_channel=source_channel,
        lead_score=lead_score.value,
        conversation_history=f"Student: {message_text}\nBot: {ai_response.reply_text}",
    )

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
