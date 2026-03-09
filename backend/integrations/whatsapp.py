"""
Meta WhatsApp Business API integration.
Handles sending messages and parsing incoming webhook payloads.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


class WhatsAppMessage:
    """Parsed incoming WhatsApp message."""

    def __init__(
        self,
        phone_number: str,
        message_text: str,
        message_id: str,
        wa_id: str,
        name: str = "",
        timestamp: str = "",
    ):
        self.phone_number = phone_number
        self.message_text = message_text
        self.message_id = message_id
        self.wa_id = wa_id
        self.name = name
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return (
            f"WhatsAppMessage(phone={self.phone_number!r}, "
            f"text={self.message_text[:40]!r})"
        )


def parse_webhook_payload(payload: Dict[str, Any]) -> List[WhatsAppMessage]:
    """
    Parse a Meta WhatsApp webhook payload and extract incoming messages.

    Returns a list of WhatsAppMessage objects (usually just one per webhook call).
    """
    messages: List[WhatsAppMessage] = []
    try:
        entries = payload.get("entry", [])
        if not isinstance(entries, list):
            return messages
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                incoming = value.get("messages", [])
                contacts = value.get("contacts", [])
                contact_map = {c["wa_id"]: c.get("profile", {}).get("name", "") for c in contacts}

                for msg in incoming:
                    if msg.get("type") != "text":
                        continue  # Only handle text messages for now
                    wa_id = msg.get("from", "")
                    messages.append(
                        WhatsAppMessage(
                            phone_number=f"+{wa_id}",
                            message_text=msg.get("text", {}).get("body", ""),
                            message_id=msg.get("id", ""),
                            wa_id=wa_id,
                            name=contact_map.get(wa_id, ""),
                            timestamp=msg.get("timestamp", ""),
                        )
                    )
    except (KeyError, TypeError) as exc:
        logger.warning("Failed to parse WhatsApp webhook payload: %s", exc)
    return messages


async def send_text_message(to: str, text: str) -> bool:
    """
    Send a plain text message via WhatsApp Business API.

    Args:
        to: Recipient phone number with country code (e.g. '+919876543210')
        text: Message body

    Returns:
        True on success, False on failure
    """
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning("WhatsApp credentials not configured — skipping send")
        return False

    # Normalize number: remove leading +
    to_normalized = to.lstrip("+")

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_normalized,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                settings.whatsapp_api_url,
                headers=headers,
                json=payload,
            )
            if response.status_code == 200:
                logger.info("Message sent to %s", to)
                return True
            else:
                logger.error(
                    "WhatsApp API error %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
    except httpx.RequestError as exc:
        logger.error("WhatsApp send request failed: %s", exc)
        return False


async def send_counsellor_alert(
    counsellor_number: str,
    student_name: str,
    student_phone: str,
    city: str,
    course_interest: str,
    lead_score: str,
) -> bool:
    """Send a hot-lead alert to a counsellor via WhatsApp."""
    alert_text = (
        f"🔥 *HOT LEAD ALERT — IIST AdmitBot*\n\n"
        f"👤 Name: {student_name or 'Unknown'}\n"
        f"📞 Phone: {student_phone}\n"
        f"🏙️ City: {city or 'Unknown'}\n"
        f"🎓 Course: {course_interest or 'Unknown'}\n"
        f"⭐ Score: {lead_score}\n\n"
        f"Please contact this student within 30 minutes. "
        f"Full chat history available in Google Sheets. 📊"
    )
    return await send_text_message(counsellor_number, alert_text)


async def send_followup_message(to: str, student_name: str) -> bool:
    """Send 48-hour follow-up message to a student."""
    name_part = f" {student_name}" if student_name else ""
    followup_text = (
        f"Hi{name_part}! 👋 This is AdmitBot from IIST.\n\n"
        f"We noticed you enquired about admissions recently. "
        f"Seats are filling up fast! 🎓\n\n"
        f"Application deadline: *June 30, 2026*\n\n"
        f"Would you like to know more or speak with a counsellor? "
        f"Just reply and we'll help you right away! 😊"
    )
    return await send_text_message(to, followup_text)


async def send_escalation_message(to: str, counsellor_name: str = "our team") -> bool:
    """Send escalation message to student when routing to counsellor."""
    text = (
        f"I understand this is important. 🤝 I'm connecting you with "
        f"{counsellor_name} from our admissions team right away.\n\n"
        f"They have your full chat history — you won't need to repeat anything. "
        f"Expect a call within 30 minutes! 📞"
    )
    return await send_text_message(to, text)
