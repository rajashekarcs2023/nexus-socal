"""
Eventbrite API tools for Stanford Women in CS: CONNECT (public agent).

Read-only access to event details and ticket classes.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

# Simple in-memory cache with TTL
_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    if key not in _CACHE:
        return None
    data, ts = _CACHE[key]
    if time.time() - ts < _CACHE_TTL_SECONDS:
        return data
    _CACHE.pop(key, None)
    return None


def _set_cache(key: str, data: Dict[str, Any]) -> None:
    _CACHE[key] = (data, time.time())


def _token() -> Optional[str]:
    tok = os.getenv("EVENTBRITE_OAUTH_TOKEN", "").strip()
    return tok or None


def _event_id() -> Optional[str]:
    eid = os.getenv("EVENTBRITE_EVENT_ID", "").strip()
    return eid or None


def _event_url() -> str:
    return os.getenv(
        "EVENTBRITE_EVENT_URL",
        "https://www.eventbrite.com/e/ubs-ps-x-fetchai-case-competition-tickets-1985241779604?aff=oddtdtcreator",
    ).strip()


def _get_json(url: str, *, token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            return {"error": "HTTP_ERROR", "status": resp.status_code, "body": resp.text}
        return resp.json() or {}


def get_event_info() -> Dict[str, Any]:
    """
    Get public event info from Eventbrite.
    Includes venue details if venue_id is present.
    """
    eid = _event_id()
    if not eid:
        return {"error": "MISSING_EVENT_ID"}

    tok = _token()
    if not tok:
        return {"error": "MISSING_TOKEN"}

    cache_key = f"event_info::{eid}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    event = _get_json(f"https://www.eventbriteapi.com/v3/events/{eid}/", token=tok)
    if event.get("error"):
        return event

    start = (event.get("start") or {}).get("local") or (event.get("start") or {}).get("utc")
    end = (event.get("end") or {}).get("local") or (event.get("end") or {}).get("utc")
    venue_id = event.get("venue_id")

    venue: dict[str, Any] | None = None
    if venue_id:
        venue_resp = _get_json(f"https://www.eventbriteapi.com/v3/venues/{venue_id}/", token=tok)
        if not venue_resp.get("error"):
            addr = venue_resp.get("address") or {}
            venue = {
                "venue_id": venue_id,
                "name": venue_resp.get("name"),
                "address_display": addr.get("localized_address_display"),
                "address": addr,
            }

    result: Dict[str, Any] = {
        "event_id": eid,
        "name": (event.get("name") or {}).get("text"),
        "description": (event.get("description") or {}).get("text"),
        "summary": event.get("summary"),
        "url": event.get("url") or _event_url(),
        "start": start,
        "end": end,
        "timezone": event.get("timezone"),
        "currency": event.get("currency"),
        "is_free": event.get("is_free"),
        "online_event": event.get("online_event"),
        "venue": venue,
    }

    _set_cache(cache_key, result)
    return result


def get_ticket_types() -> Dict[str, Any]:
    """
    Get public ticket classes for the event.
    """
    eid = _event_id()
    if not eid:
        return {"error": "MISSING_EVENT_ID"}

    tok = _token()
    if not tok:
        return {"error": "MISSING_TOKEN"}

    cache_key = f"ticket_types::{eid}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    data = _get_json(f"https://www.eventbriteapi.com/v3/events/{eid}/ticket_classes/", token=tok)
    if data.get("error"):
        return data

    tickets = []
    for tc in (data.get("ticket_classes") or []):
        if not isinstance(tc, dict):
            continue
        if tc.get("hidden"):
            continue

        cost = tc.get("cost") or {}
        total = tc.get("quantity_total")
        sold = tc.get("quantity_sold", 0)
        remaining = (total - sold) if isinstance(total, int) else None

        if remaining is not None:
            if remaining <= 0:
                availability = "Sold Out"
            elif remaining < 10:
                availability = f"Only {remaining} left"
            else:
                availability = "Available"
        else:
            availability = "Available"

        tickets.append(
            {
                "name": tc.get("name"),
                "description": tc.get("description") or "",
                "price": cost.get("display", "Free"),
                "currency": cost.get("currency"),
                "free": bool(tc.get("free", False)),
                "availability": availability,
                "on_sale_status": tc.get("on_sale_status"),
            }
        )

    result = {"event_id": eid, "tickets": tickets, "event_url": _event_url()}
    _set_cache(cache_key, result)
    return result


def lookup_order(order_id: str, retry_count: int = 3, retry_delay: float = 3.0) -> Dict[str, Any]:
    """
    Look up a specific Eventbrite order by ID.

    Note: orders can take a few seconds to be available via API after creation, so we retry.
    Returns: order details including attendees, costs, and a mytickets URL.
    """
    tok = _token()
    if not tok:
        return {"error": "MISSING_TOKEN"}

    order_id = str(order_id).strip()
    if not order_id:
        return {"error": "MISSING_ORDER_ID"}

    url = f"https://www.eventbriteapi.com/v3/orders/{order_id}/"
    headers = {"Authorization": f"Bearer {tok}"}

    last_error: Dict[str, Any] | None = None
    data: Dict[str, Any] | None = None

    for attempt in range(retry_count):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, headers=headers, params={"expand": "attendees,costs"})
                if resp.status_code >= 400:
                    body: Any = resp.text
                    try:
                        body = resp.json()
                    except Exception:
                        pass

                    # Retry common timing issue (INVALID_ARGUMENT shortly after purchase)
                    if resp.status_code == 400 and attempt < retry_count - 1:
                        err_type = body.get("error", "") if isinstance(body, dict) else ""
                        if err_type == "INVALID_ARGUMENT":
                            time.sleep(retry_delay)
                            last_error = {"error": "HTTP_ERROR", "status": resp.status_code, "body": body}
                            continue

                    return {"error": "HTTP_ERROR", "status": resp.status_code, "body": body}

                data = resp.json() or {}
                last_error = None
                break
        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(retry_delay)
                last_error = {"error": "EXCEPTION", "message": str(e)}
                continue
            return {"error": "EXCEPTION", "message": str(e)}

    if last_error:
        return last_error
    if not data:
        return {"error": "EMPTY_RESPONSE", "message": "Eventbrite API returned empty response"}

    costs = data.get("costs", {}) or {}
    attendees = data.get("attendees", []) or []
    event_id = data.get("event_id")
    oid = data.get("id") or order_id

    attendee_list = []
    for att in attendees:
        if not isinstance(att, dict):
            continue
        barcodes = att.get("barcodes", []) or []
        barcode_data = barcodes[0] if isinstance(barcodes, list) and barcodes else None
        barcode = barcode_data.get("barcode") if isinstance(barcode_data, dict) else None

        ticket_url = None
        if barcode and event_id and oid:
            ticket_url = f"https://www.eventbrite.com/myticket/eid/{event_id}/oid/{oid}/barcode/{barcode}/"

        attendee_list.append(
            {
                "name": (att.get("profile") or {}).get("name"),
                "email": (att.get("profile") or {}).get("email"),
                "ticket_type": att.get("ticket_class_name"),
                "barcode": barcode,
                "ticket_url": ticket_url,
                "attendee_id": att.get("id"),
            }
        )

    primary_email = data.get("email") or (attendee_list[0].get("email") if attendee_list else None)

    gross_value = None
    try:
        gross_cents = (costs.get("gross") or {}).get("value")
        if gross_cents is not None:
            gross_value = gross_cents / 100.0
    except Exception:
        gross_value = None

    return {
        "order_id": oid,
        "name": data.get("name"),
        "email": primary_email,
        "status": data.get("status"),
        "created": data.get("created"),
        "costs": {
            "base_price": (costs.get("base_price") or {}).get("display", "N/A"),
            "eventbrite_fee": (costs.get("eventbrite_fee") or {}).get("display", "N/A"),
            "gross": (costs.get("gross") or {}).get("display", "N/A"),
            "gross_value": gross_value,
        },
        "event_id": event_id,
        "attendees": attendee_list,
        "attendee_count": len(attendee_list),
        "eventbrite_tickets_url": f"https://www.eventbrite.com/mytickets/?email={primary_email}" if primary_email else None,
    }

