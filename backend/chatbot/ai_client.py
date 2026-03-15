"""
Multi-provider AI client for IIST AdmitBot.
Supports Groq (free), OpenAI, Google Gemini, and a rule-based fallback.

Priority order when AI_PROVIDER=auto (default):
  Groq → OpenAI → Gemini → rule-based keyword fallback

Configure via .env:
  AI_PROVIDER=auto|groq|openai|gemini
  GROQ_API_KEY=gsk_...        (free at console.groq.com)
  OPENAI_API_KEY=sk-...
  GEMINI_API_KEY=...
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class AIResponse:
    """Parsed response from any AI provider."""

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


# Backward-compatibility alias kept for any external code that imported GeminiResponse
GeminiResponse = AIResponse


# ---------------------------------------------------------------------------
# Response parser (shared by all providers)
# ---------------------------------------------------------------------------

def _parse_structured_output(raw: str) -> AIResponse:
    """
    Parse AI output that contains:
    1. A human-readable reply
    2. An optional ```json ... ``` metadata block
    """
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    structured: Dict[str, Any] = {}
    reply_text = raw.strip()

    if json_match:
        json_str = json_match.group(1).strip()
        try:
            structured = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI JSON block: %s", json_str[:200])
        reply_text = raw[: json_match.start()].strip()

    return AIResponse(
        reply_text=reply_text,
        intent_score=structured.get("intent_score"),
        extracted_data=structured.get("extracted_data", {}),
        needs_escalation=bool(structured.get("needs_escalation", False)),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# Provider: OpenAI-compatible (Groq + OpenAI use same format)
# ---------------------------------------------------------------------------

async def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: float,
) -> AIResponse:
    """Call any OpenAI-compatible chat completions endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 512,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(base_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    raw_text: str = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not raw_text:
        raise ValueError("Empty response from AI provider")
    return _parse_structured_output(raw_text)


# ---------------------------------------------------------------------------
# Provider: Google Gemini
# ---------------------------------------------------------------------------

async def _call_gemini(prompt: str, timeout: float) -> AIResponse:
    """Call Google Gemini API."""
    url = f"{GEMINI_API_BASE}/{settings.gemini_model}:generateContent"
    params = {"key": settings.gemini_api_key}
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
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

    raw_text: str = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    if not raw_text:
        raise ValueError("Empty response from Gemini API")
    return _parse_structured_output(raw_text)


# ---------------------------------------------------------------------------
# Fallback: rule-based knowledge base responder
# (works with zero external APIs — ideal for local testing)
# ---------------------------------------------------------------------------

_RULE_PATTERNS: List[tuple[str, str]] = [
    (r"cse|computer\s*science", "cse"),
    (r"\bece\b|electronics", "ece"),
    (r"\bit\b|information\s*tech", "it"),
    (r"mech(anical)?", "mechanical"),
    (r"\bcivil\b", "civil"),
    (r"\bmba\b", "mba"),
    (r"\bhostel\b", "hostel"),
    (r"scholarship|waiver|concession", "scholarship"),
    (r"fee[s]?|kitna|amount|cost|charges", "fees"),
    (r"placement|package|lpa|salary|recruiter", "placement"),
    (r"eligib|percentile|jee|12th|marks", "eligibility"),
    (r"deadline|last\s*date|last\s*day|closing", "deadline"),
    (r"apply|admission|form|register|process|steps", "admission_process"),
    (r"\bdocument", "documents"),
    (r"facilit|lab|campus|wifi|transport|bus|sport|gym|canteen", "facilities"),
]

_RULE_RESPONSES: Dict[str, str] = {
    "cse": (
        "B.Tech CSE at IIST — 120 seats, 4 years 🎓\n"
        "Eligibility: JEE Main 85+ percentile OR 12th PCM 75%+\n"
        "Annual Fee: ₹85,000 | Total 4-year: ₹3,40,000\n"
        "Apply now: iist.ac.in/apply | admissions@iist.ac.in"
    ),
    "ece": (
        "B.Tech ECE at IIST — 60 seats, 4 years 📡\n"
        "Eligibility: JEE Main 70+ percentile OR 12th PCM 65%+\n"
        "Annual Fee: ₹82,000 | Total 4-year: ₹3,28,000\n"
        "Apply now: iist.ac.in/apply"
    ),
    "it": (
        "B.Tech IT at IIST — 60 seats, 4 years 💻\n"
        "Eligibility: JEE Main 75+ percentile OR 12th PCM 70%+\n"
        "Annual Fee: ₹82,000 | Total 4-year: ₹3,28,000\n"
        "Apply now: iist.ac.in/apply"
    ),
    "mechanical": (
        "B.Tech Mechanical at IIST — 60 seats, 4 years ⚙️\n"
        "Eligibility: JEE Main 60+ percentile OR 12th PCM 60%+\n"
        "Annual Fee: ₹78,000 | Total 4-year: ₹3,12,000\n"
        "Apply now: iist.ac.in/apply"
    ),
    "civil": (
        "B.Tech Civil at IIST — 60 seats, 4 years 🏗️\n"
        "Eligibility: JEE Main 55+ percentile OR 12th PCM 55%+\n"
        "Annual Fee: ₹75,000 | Total 4-year: ₹3,00,000\n"
        "Apply now: iist.ac.in/apply"
    ),
    "mba": (
        "MBA at IIST — 60 seats, 2 years 📊\n"
        "Eligibility: Graduation 50%+ | CAT/MAT score preferred\n"
        "Annual Fee: ₹65,000 | Total 2-year: ₹1,30,000\n"
        "Apply now: iist.ac.in/apply"
    ),
    "hostel": (
        "IIST Hostel 🏠\n"
        "Boys Hostel: ₹45,000/year (room + meals)\n"
        "Girls Hostel: ₹48,000/year with 24/7 security\n"
        "Includes Wi-Fi, sports facilities, canteen!"
    ),
    "scholarship": (
        "IIST Scholarships 🌟\n"
        "• Merit: 25% off for JEE Main 95+ percentile\n"
        "• SC/ST: Government scholarship + 10% institutional concession\n"
        "• Girl Child: 10% fee waiver for female students\n"
        "• Sports: Up to 20% off for state/national level athletes"
    ),
    "fees": (
        "IIST Annual Fees 💰\n"
        "CSE: ₹85,000 | ECE/IT: ₹82,000\n"
        "Mechanical: ₹78,000 | Civil: ₹75,000 | MBA: ₹65,000\n"
        "Hostel extra: ₹45,000–₹48,000/year. Scholarships available!"
    ),
    "placement": (
        "IIST Placements 2025 🎯\n"
        "Average: ₹6.2 LPA | Highest: ₹18 LPA (Microsoft, Pune)\n"
        "Top Recruiters: TCS, Infosys, Wipro, Capgemini, L&T, HCL\n"
        "CSE 92% | ECE 85% | IT 88% placement rate"
    ),
    "eligibility": (
        "IIST Eligibility Criteria 📋\n"
        "CSE: JEE 85+ OR 12th PCM 75%\n"
        "IT: JEE 75+ OR 12th PCM 70%\n"
        "ECE: JEE 70+ OR 12th PCM 65%\n"
        "Mechanical: JEE 60+ OR 12th PCM 60%"
    ),
    "admission_process": (
        "IIST Admission Process 📝\n"
        "1. Register at iist.ac.in/apply\n"
        "2. Pay ₹1,000 application fee\n"
        "3. Submit JEE scorecard + 12th marksheet + ID proof\n"
        "4. Counselling call within 24 hours\n"
        "5. Confirm seat with ₹25,000 advance (adjustable)"
    ),
    "deadline": (
        "IIST 2026 Admission Dates 📅\n"
        "Application Deadline: June 30, 2026\n"
        "Seat Confirmation: July 10, 2026\n"
        "Orientation Day: July 15, 2026\n"
        "Apply now — seats filling fast! 🚀"
    ),
    "documents": (
        "Documents Required for IIST Admission 📄\n"
        "• JEE Main scorecard\n"
        "• 12th and 10th marksheets\n"
        "• Aadhar card + passport photos (4)\n"
        "• Caste certificate (if applicable)\n"
        "• ₹1,000 application fee (online/DD)"
    ),
    "facilities": (
        "IIST Campus Facilities 🏫\n"
        "Labs: Computer, electronics, mechanical workshops\n"
        "Sports: Cricket, basketball, gym, indoor games\n"
        "Transport: College bus ₹12,000/year | Canteen | Wi-Fi\n"
        "Boys & girls hostel on campus"
    ),
}


def _rule_based_response(message: str) -> AIResponse:
    """
    Return a keyword-matched response from the IIST knowledge base.
    This is the zero-dependency fallback — no API key required.
    """
    text_lower = message.lower()

    for pattern, key in _RULE_PATTERNS:
        if re.search(pattern, text_lower):
            return AIResponse(
                reply_text=_RULE_RESPONSES[key],
                intent_score="Warm",
                extracted_data={},
                needs_escalation=False,
            )

    # Generic greeting / unknown query
    return AIResponse(
        reply_text=(
            "Hi! 👋 I'm AdmitBot, your IIST admission assistant!\n"
            "I can help with: courses, fees, eligibility, scholarships, "
            "hostel, placements, and the admission process.\n"
            "What would you like to know? 😊\n"
            "Or contact us directly: admissions@indoreinstitute.com | 1800-103-3069"
        ),
        intent_score="Cold",
        extracted_data={},
        needs_escalation=False,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_response(
    prompt: str,
    timeout: float = 30.0,
) -> AIResponse:
    """
    Generate a response using the configured AI provider.

    Provider resolution when AI_PROVIDER=auto (default):
      1. Groq (if GROQ_API_KEY set)
      2. OpenAI (if OPENAI_API_KEY set)
      3. Gemini (if GEMINI_API_KEY set)
      4. Rule-based fallback (always available)
    """
    provider = settings.ai_provider.lower()

    if provider == "groq":
        candidates = ["groq"]
    elif provider == "openai":
        candidates = ["openai"]
    elif provider == "gemini":
        candidates = ["gemini"]
    else:  # "auto"
        candidates = ["groq", "openai", "gemini"]

    for p in candidates:
        try:
            if p == "groq" and settings.groq_api_key:
                logger.debug("Using Groq AI provider")
                return await _call_openai_compat(
                    "https://api.groq.com/openai/v1/chat/completions",
                    settings.groq_api_key,
                    "llama-3.3-70b-versatile",
                    prompt,
                    timeout,
                )
            elif p == "openai" and settings.openai_api_key:
                logger.debug("Using OpenAI provider")
                return await _call_openai_compat(
                    "https://api.openai.com/v1/chat/completions",
                    settings.openai_api_key,
                    "gpt-4o-mini",
                    prompt,
                    timeout,
                )
            elif p == "gemini" and settings.gemini_api_key:
                logger.debug("Using Gemini provider")
                return await _call_gemini(prompt, timeout)
        except Exception as exc:
            logger.warning("AI provider '%s' failed: %s — trying next", p, exc)
            continue

    # Extract the student message from the full prompt for keyword matching
    if "Student message:" in prompt:
        student_message = prompt.split("Student message:")[-1].strip()
    else:
        student_message = prompt

    logger.info("No AI provider available — using rule-based fallback")
    return _rule_based_response(student_message)
