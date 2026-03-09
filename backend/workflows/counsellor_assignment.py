"""
Round-robin counsellor assignment logic.
Distributes hot leads evenly across available counsellors.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# Module-level counter for round-robin assignment
_counsellor_index = 0


def get_next_counsellor(counsellors: List[str]) -> str:
    """
    Return the next counsellor in the round-robin rotation.

    Args:
        counsellors: List of counsellor WhatsApp numbers

    Returns:
        The selected counsellor's phone number
    """
    global _counsellor_index

    if not counsellors:
        raise ValueError("No counsellors configured")

    counsellor = counsellors[_counsellor_index % len(counsellors)]
    _counsellor_index += 1
    logger.debug("Assigned to counsellor: %s (index %d)", counsellor, _counsellor_index - 1)
    return counsellor


def reset_index() -> None:
    """Reset the round-robin counter. Used in tests."""
    global _counsellor_index
    _counsellor_index = 0
