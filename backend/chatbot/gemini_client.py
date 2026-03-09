"""
Google Gemini AI client for IIST AdmitBot.
Handles response generation and parsing of structured data from AI output.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiResponse:
    """Parsed response from Gemini AI."""

    def __init__(
        self,
        reply_text: str,
        intent_score: Optional[str] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
        needs_escalation: bool = False,
        raw_text: str = "",
    ):
        self.reply_text = reply_text
        self.intent_score = intent_score
        self.extracted_data = extracted_data or {}
        self.needs_escalation = needs_escalation
        self.raw_text = raw_text


def _parse_gemini_output(raw: str) -> GeminiResponse:
    """
    Parse Gemini's output which contains:
    1. Human-readable reply text
    2. A JSON block with structured metadata
    """
    # Try to extract the JSON block
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    structured: Dict[str, Any] = {}
    reply_text = raw.strip()

    if json_match:
        json_str = json_match.group(1).strip()
        try:
            structured = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Gemini JSON block: %s", json_str[:200])
        # Remove JSON block from reply text
        reply_text = raw[: json_match.start()].strip()

    return GeminiResponse(
        reply_text=reply_text,
        intent_score=structured.get("intent_score"),
        extracted_data=structured.get("extracted_data", {}),
        needs_escalation=bool(structured.get("needs_escalation", False)),
        raw_text=raw,
    )


async def generate_response(
    prompt: str,
    timeout: float = 30.0,
) -> GeminiResponse:
    """
    Call Gemini API and return a parsed GeminiResponse.

    Args:
        prompt: The full prompt (system + conversation context + student message)
        timeout: Request timeout in seconds

    Returns:
        GeminiResponse with reply text and structured metadata
    """
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — returning fallback response")
        return GeminiResponse(
            reply_text=(
                "Hi! 👋 I'm AdmitBot, your IIST admission assistant. "
                "I'd love to help you! Please contact our admissions team at "
                "admissions@iist.ac.in or call us at +91-731-XXXXXXX. 📞"
            ),
            needs_escalation=True,
        )

    url = f"{GEMINI_API_BASE}/{settings.gemini_model}:generateContent"
    params = {"key": settings.gemini_api_key}
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
            "topP": 0.9,
        },
        "safetySettings": [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE",
            }
        ],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, params=params, json=payload)
        response.raise_for_status()
        data = response.json()

    raw_text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    if not raw_text:
        logger.warning("Empty response from Gemini API")
        return GeminiResponse(
            reply_text=(
                "I'm having a little trouble right now. 🙏 "
                "Please contact our team: admissions@iist.ac.in"
            ),
            needs_escalation=True,
        )

    return _parse_gemini_output(raw_text)
