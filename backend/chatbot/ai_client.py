"""Groq-first AI client for IIST AdmitBot with rule-based fallback."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


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

    if not reply_text:
        # Guard against providers returning only metadata JSON without human text.
        reply_text = (
            "Thanks for your question. I can help with courses, fees, eligibility, "
            "scholarships, hostel, and admissions process."
        )

    return AIResponse(
        reply_text=reply_text,
        intent_score=structured.get("intent_score"),
        extracted_data=structured.get("extracted_data", {}),
        needs_escalation=bool(structured.get("needs_escalation", False)),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# Provider: Groq
# ---------------------------------------------------------------------------

async def _call_groq(
    prompt: str,
    timeout: float,
) -> AIResponse:
    """Call Groq chat completions endpoint."""
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 512,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
        )
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
    (r"admission\s*timings?|office\s*timings?|working\s*hours?|open\s*time|close\s*time", "admission_timing"),
    (r"visit|campus\s*tour|college\s*tour|college\s*visit|campus\s*visit", "campus_visit"),
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
    "admission_timing": (
        "IIST Admissions Office Timings 🕘\n"
        "Monday to Saturday: 10:00 AM - 5:00 PM\n"
        "You can submit forms online anytime at iist.ac.in/apply\n"
        "For same-day support, call 1800-103-3069."
    ),
    "campus_visit": (
        "Campus visit is possible ✅\n"
        "Best hours: 10:00 AM - 4:00 PM (Mon-Sat)\n"
        "Share your preferred day and branch; our team will schedule a guided visit.\n"
        "Call 1800-103-3069 for quick slot confirmation."
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


def generate_faq_fallback_response(message: str) -> AIResponse:
    """Public wrapper for deterministic FAQ response generation."""
    return _rule_based_response(message)


def _extract_student_message_from_prompt(prompt: str) -> str:
    """Extract only the user message from the full system prompt template."""
    # Preferred path: capture text between "Student message:" and trailing instructions.
    match = re.search(
        r"Student message:\s*(.*?)\n\s*Respond naturally in the student's language",
        prompt,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # Fallback path for unexpected template changes.
    if "Student message:" in prompt:
        tail = prompt.split("Student message:", 1)[-1].strip()
        return tail.splitlines()[0].strip()

    return prompt.strip()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_response(
    prompt: str,
    timeout: float = 10.0,
) -> AIResponse:
    """
    Generate a response using Groq. If unavailable, use rule-based fallback.
    """
    provider = settings.ai_provider.lower()

    if provider not in {"groq", "auto"}:
        logger.warning("AI_PROVIDER '%s' is not supported; enforcing Groq-only mode", provider)

    if settings.groq_api_key:
        try:
            logger.debug("Using Groq AI provider")
            return await _call_groq(prompt, timeout)
        except Exception as exc:
            logger.warning("Groq provider failed: %s — using rule-based fallback", exc)

    # Extract only student text from the full prompt for fallback keyword matching.
    student_message = _extract_student_message_from_prompt(prompt)

    logger.info("No AI provider available — using rule-based fallback")
    return _rule_based_response(student_message)
