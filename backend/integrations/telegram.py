"""
Telegram Bot API integration.
Handles parsing incoming Telegram webhook updates and sending bot replies.
"""

import logging
from typing import Any, Dict, List

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


class TelegramMessage:
    """Parsed incoming Telegram message."""

    def __init__(
        self,
        chat_id: str,
        message_text: str,
        message_id: str,
        user_id: str,
        name: str = "",
        username: str = "",
    ):
        self.chat_id = chat_id
        self.message_text = message_text
        self.message_id = message_id
        self.user_id = user_id
        self.name = name
        self.username = username

    def __repr__(self) -> str:
        return (
            f"TelegramMessage(chat_id={self.chat_id!r}, "
            f"text={self.message_text[:40]!r})"
        )


def parse_webhook_update(payload: Dict[str, Any]) -> List[TelegramMessage]:
    """
    Parse a Telegram webhook update payload and extract text messages.

    Returns a list of TelegramMessage objects.
    """
    messages: List[TelegramMessage] = []

    try:
        message = payload.get("message")
        if not isinstance(message, dict):
            return messages

        text = message.get("text", "")
        if not text:
            return messages

        chat = message.get("chat", {})
        user = message.get("from", {})

        first_name = user.get("first_name", "")
        last_name = user.get("last_name", "")
        full_name = (f"{first_name} {last_name}").strip()

        messages.append(
            TelegramMessage(
                chat_id=str(chat.get("id", "")),
                message_text=text,
                message_id=str(message.get("message_id", "")),
                user_id=str(user.get("id", "")),
                name=full_name,
                username=user.get("username", ""),
            )
        )
    except (KeyError, TypeError) as exc:
        logger.warning("Failed to parse Telegram webhook payload: %s", exc)

    return messages


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a plain text message via Telegram Bot API."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured — skipping send")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("Telegram message sent to chat_id=%s", chat_id)
                return True
            logger.error(
                "Telegram API error %s: %s",
                response.status_code,
                response.text[:200],
            )
            return False
    except httpx.RequestError as exc:
        logger.error("Telegram send request failed: %s", exc)
        return False
