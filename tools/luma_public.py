"""
Luma tools for SoCal Claude Hackathon (public agent).

Provides static event info and registration URL.
Guest lookup can be enabled later with the event owner's API key.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def _event_url() -> str:
    return os.getenv(
        "LUMA_EVENT_URL",
        "https://luma.com/dj0aohkq",
    ).strip()


def get_event_info() -> Dict[str, Any]:
    """
    Get event info (static since co-host API key can't read this event).
    """
    return {
        "event_id": "evt-MwKhJ4chKxHBsRk",
        "name": "SoCal Claude Hackathon",
        "description": "A hackathon hosted by UCLA Claude Builder Club, Nexus & Fetch.ai Innovation Lab.",
        "url": _event_url(),
        "start": "2026-04-19T09:00:00",
        "timezone": "America/Los_Angeles",
        "venue": {
            "name": "UCLA Ackerman Union",
            "address_display": "UCLA Ackerman Union, Los Angeles, CA",
        },
        "is_free": True,
        "luma_event_url": _event_url(),
    }


def get_registration_url() -> Dict[str, Any]:
    """
    Return the Luma registration URL for the event.
    """
    return {
        "url": _event_url(),
        "event_name": "SoCal Claude Hackathon",
        "action": "register",
    }
