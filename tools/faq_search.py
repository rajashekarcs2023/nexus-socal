"""
FAQ context for SoCal Claude Hackathon.

Loads FAQ from faq.md at module import time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


LUMA_URL = os.getenv(
    "LUMA_EVENT_URL",
    "https://luma.com/dj0aohkq",
).strip()

# Load FAQ from faq.md at module level
_FAQ_PATH = Path(__file__).resolve().parent.parent / "faq.md"
try:
    FAQ_CONTENT = _FAQ_PATH.read_text(encoding="utf-8")
except Exception:
    FAQ_CONTENT = "FAQ file not found. Please visit https://luma.com/dj0aohkq for event details."


def get_event_faq_context() -> Dict[str, Any]:
    """
    FAQ context for the SoCal Claude Hackathon, loaded from faq.md.
    """
    return {
        "event_name": "SoCal Claude Hackathon",
        "overview": "A one-day intercollegiate AI hackathon hosted by UCLA, USC, Caltech, and Nexus at UCLA Ackerman Grand Ballroom on April 19, 2026.",
        "faq_content": FAQ_CONTENT,
        "luma_url": LUMA_URL,
        "registration_url": LUMA_URL,
        "answering_policy": (
            "Use the FAQ content for event details. "
            "For questions not covered in FAQ, refer users to the Luma event page."
        ),
    }

