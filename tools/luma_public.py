"""
Luma tools for SoCal Claude Hackathon (public agent).

Provides static event info, registration URL, and guest status lookup.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

LUMA_API_BASE = "https://public-api.luma.com"


def _event_id() -> str:
    return os.getenv("LUMA_EVENT_ID", "evt-KvLLM707XPkTH3N").strip()


def _event_name() -> str:
    return os.getenv("LUMA_EVENT_NAME", "SoCal Claude Hackathon").strip()


def _event_url() -> str:
    return os.getenv(
        "LUMA_EVENT_URL",
        "https://lu.ma/event/evt-KvLLM707XPkTH3N",
    ).strip()


def get_event_info() -> Dict[str, Any]:
    """
    Get event info (static since co-host API key can't read this event).
    """
    return {
        "event_id": _event_id(),
        "name": _event_name(),
        "description": "A one-day intercollegiate AI hackathon hosted by UCLA, USC, Caltech, and Nexus for social impact, powered by Anthropic.",
        "url": _event_url(),
        "start": "2026-04-19T08:30:00",
        "timezone": "America/Los_Angeles",
        "venue": {
            "name": "Grand Ackerman Ballroom, UCLA",
            "address_display": "Grand Ackerman Ballroom, UCLA, Los Angeles, CA",
        },
        "is_free": True,
        "luma_event_url": _event_url(),
    }


def get_registration_url() -> Dict[str, Any]:
    """
    Return the Luma registration card in the format the ASI:One frontend expects.

    Frontend renders this as an interactive registration card when it detects:
      type == "luma_event" AND event_id.startsWith("evt-")
    """
    return {
        "type": "luma_event",
        "action": "Register for Event",
        "event_id": _event_id(),
        "event_url": _event_url(),
        "event_name": _event_name(),
        "event_date": "2026-04-19T08:30:00-07:00",
    }


def check_guest_status(email: str) -> Dict[str, Any]:
    """
    Look up a guest's registration status on Luma by email.

    Calls GET /v1/event/get-guest with the owner API key.
    Returns a dict with 'found', 'approval_status', 'friendly_status', etc.
    """
    api_key = os.getenv("LUMA_API_KEY", "").strip()
    if not api_key:
        return {"found": False, "error": "LUMA_API_KEY not configured"}

    event_id = _event_id()
    try:
        resp = requests.get(
            f"{LUMA_API_BASE}/v1/event/get-guest",
            params={"event_id": event_id, "id": email},
            headers={"x-luma-api-key": api_key},
            timeout=10,
        )
        if resp.status_code == 404:
            return {"found": False, "email": email, "event_id": event_id}
        if resp.status_code != 200:
            logger.warning("[luma] get-guest %s/%s returned %s", event_id, email, resp.status_code)
            return {"found": False, "email": email, "error": f"API returned {resp.status_code}"}

        data = resp.json()
        guest = data.get("guest", {})
        approval = guest.get("approval_status", "unknown")

        friendly_map = {
            "approved": "approved",
            "pending_approval": "pending approval",
            "declined": "declined",
            "waitlist": "on the waitlist",
            "waitlisted": "on the waitlist",
            "invited": "invited (not yet registered)",
        }

        return {
            "found": True,
            "email": email,
            "event_id": event_id,
            "event_name": _event_name(),
            "approval_status": approval,
            "friendly_status": friendly_map.get(approval, approval),
            "guest_name": guest.get("user_name"),
        }
    except Exception as exc:
        logger.warning("[luma] check_guest_status failed: %s", exc)
        return {"found": False, "email": email, "error": str(exc)}
