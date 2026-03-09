"""
Lead scoring logic for IIST AdmitBot.
Classifies each student enquiry as Hot, Warm, or Cold based on intent signals.
"""

import re
from enum import Enum
from typing import Optional


class LeadScore(str, Enum):
    HOT = "Hot"
    WARM = "Warm"
    COLD = "Cold"


# Signals that indicate high purchase intent
_HOT_SIGNALS = [
    r"\badmission\s*(lena|chahiye|karna|confirm|book)\b",
    r"\bapply\s*(karna|kaise|now|today)\b",
    r"\bfees?\s*(kitni|kya|pay|jama|deposit)\b",
    r"\bdocument(s)?\s*(chahiye|submit|required|kya)\b",
    r"\b(seat|seats)\s*(available|hai|milegi|left)\b",
    r"\bjoin\s*(karna|want|chahta|chahti)\b",
    r"\bconfirm\b",
    r"\benroll(ment)?\b",
    r"\blast\s*date\b",
    r"\bdeadline\b",
    r"\bcounsell?or\s*(se|baat|talk|call)\b",
    r"\bcall\s*(me|karo|back|chahiye)\b",
    r"\bvisit\s*(campus|college|karna)\b",
    r"\bhow\s+to\s+apply\b",
    r"\bapplication\s*(form|process|fee)\b",
    r"\b(today|aaj|kal|tomorrow)\b",
]

# Signals that indicate medium interest
_WARM_SIGNALS = [
    r"\bpercentile\b",
    r"\bjee\b",
    r"\b12th?\b",
    r"\beligib(le|ility)\b",
    r"\bscholars?hips?\b",
    r"\bhostel\b",
    r"\bplacemen(t|ts)\b",
    r"\bfees?\b",
    r"\bkurs?e\b",
    r"\bbranch\b",
    r"\bcse|ece|mech|civil|b\.?tech|btech\b",
    r"\binform(ation|ation)?\b",
    r"\btell\s+me\b",
    r"\bbatao\b",
    r"\bkya\s+hai\b",
    r"\bhoga\b",
    r"\bkaise\b",
    r"\bcampus\b",
    r"\bfacilities?\b",
    r"\binterested\b",
]


def score_lead(
    message: str,
    ai_score: Optional[str] = None,
    has_phone: bool = False,
    has_name: bool = False,
    has_score: bool = False,
) -> LeadScore:
    """
    Score a lead based on message content and extracted data signals.

    Priority:
    1. If Gemini AI provides a score, trust it (it has full conversation context)
    2. Otherwise, use rule-based scoring

    Args:
        message: The student's message text
        ai_score: Optional score string from Gemini AI ('Hot', 'Warm', 'Cold')
        has_phone: Whether a phone number was extracted
        has_name: Whether a name was extracted
        has_score: Whether a JEE/12th score was extracted

    Returns:
        LeadScore enum value
    """
    # Trust AI score if valid
    if ai_score:
        normalized = ai_score.strip().capitalize()
        if normalized in (LeadScore.HOT, LeadScore.WARM, LeadScore.COLD):
            return LeadScore(normalized)

    text_lower = message.lower()

    # Count hot signals
    hot_count = sum(
        1 for pattern in _HOT_SIGNALS if re.search(pattern, text_lower)
    )

    # Boost score if student shared contact data
    data_points = sum([has_phone, has_name, has_score])

    if hot_count >= 1 or (data_points >= 2 and has_phone):
        return LeadScore.HOT

    # Count warm signals
    warm_count = sum(
        1 for pattern in _WARM_SIGNALS if re.search(pattern, text_lower)
    )

    if warm_count >= 1 or data_points >= 1:
        return LeadScore.WARM

    return LeadScore.COLD
