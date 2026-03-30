"""
Stanford Women in CS: CONNECT — Public agent.

Eventbrite-first event helper with OpenAI web search fallback.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import sentry_sdk
from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from tools import eventbrite_public, openai_client  # noqa: E402

# Config
AGENT_NAME = os.getenv("AGENT_NAME", "stanfordwics-public-agent")
AGENT_SEED = os.getenv("AGENT_SEED", "stanfordwics_connect_public_agent_rajstanford")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8004"))
AGENTVERSE_URL = os.getenv("AGENTVERSE_URL", "https://agentverse.ai")

# Optional Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", os.getenv("ENVIRONMENT", "production")).strip()
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or "0")
SENTRY_RELEASE = os.getenv("SENTRY_RELEASE", AGENT_NAME).strip()
SENTRY_ENABLED = bool(SENTRY_DSN)

if SENTRY_ENABLED:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT or "production",
        release=SENTRY_RELEASE or AGENT_NAME,
        server_name=AGENT_NAME,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )


def _sentry_breadcrumb(stage: str, data: dict | None = None) -> None:
    if not SENTRY_ENABLED:
        return
    sentry_sdk.add_breadcrumb(category="stage", message=stage, level="info", data=data or {})


def _sentry_capture_exception(e: Exception, *, stage: str, data: dict | None = None) -> None:
    if not SENTRY_ENABLED:
        return
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("stage", stage)
        if data:
            for k, v in data.items():
                scope.set_extra(k, v)
        sentry_sdk.capture_exception(e)


# Create agent (compatible across uagents versions)
_agent_kwargs = {
    "name": AGENT_NAME,
    "seed": AGENT_SEED,
    "port": AGENT_PORT,
    "mailbox": True,
    "agentverse": AGENTVERSE_URL,
    "handle_messages_concurrently": True,
}
try:
    agent = Agent(**_agent_kwargs)
except TypeError:
    _agent_kwargs.pop("handle_messages_concurrently", None)
    agent = Agent(**_agent_kwargs)

chat_proto = Protocol(spec=chat_protocol_spec)

SESSIONS_KEY = "wics_sessions"


def _truncate_for_log(text: str, limit: int = 300) -> str:
    cleaned = (text or "").replace("\n", "\\n")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "...(truncated)"


def _get_session_key(ctx: Context, sender: str) -> str:
    chat_session = ctx.session if hasattr(ctx, "session") else None
    return f"{sender}_{chat_session}" if chat_session else sender


def _get_session(ctx: Context, sender: str) -> dict:
    session_key = _get_session_key(ctx, sender)
    try:
        sessions = ctx.storage.get(SESSIONS_KEY) or {}
    except Exception:
        sessions = {}

    if session_key not in sessions:
        sessions[session_key] = {"history": [], "last_seen": datetime.now(timezone.utc).isoformat()}
        ctx.storage.set(SESSIONS_KEY, sessions)
    return sessions[session_key]


def _save_session(ctx: Context, sender: str, session: dict) -> None:
    session_key = _get_session_key(ctx, sender)
    try:
        sessions = ctx.storage.get(SESSIONS_KEY) or {}
        session["last_seen"] = datetime.now(timezone.utc).isoformat()
        sessions[session_key] = session
        ctx.storage.set(SESSIONS_KEY, sessions)
    except Exception as e:
        ctx.logger.error(f"Failed to save session: {e}")


def _extract_text(msg: ChatMessage) -> str:
    parts = []
    for item in msg.content or []:
        if isinstance(item, TextContent) and item.text:
            parts.append(item.text)
    return "\n".join(parts).strip()


@agent.on_event("startup")
async def on_startup(ctx: Context):
    ctx.logger.info(f"🎓 {AGENT_NAME} started. Address: {agent.wallet.address()}")
    if SENTRY_ENABLED:
        ctx.logger.info(f"🛰️  Sentry enabled (env={SENTRY_ENVIRONMENT})")

    ctx.logger.info("🔥 Pre-warming Eventbrite cache...")
    try:
        _sentry_breadcrumb("startup_cache_prewarm_start")
        eventbrite_public.get_event_info()
        eventbrite_public.get_ticket_types()
        ctx.logger.info("✅ Cache pre-warmed (event info + ticket types)")
        _sentry_breadcrumb("startup_cache_prewarm_ok")
    except Exception as e:
        ctx.logger.warning(f"⚠️ Cache pre-warming failed: {e}")
        _sentry_capture_exception(e, stage="startup_cache_prewarm")


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))

    chat_session = ctx.session if hasattr(ctx, "session") else None
    incoming_msg_id = str(msg.msg_id) if getattr(msg, "msg_id", None) else None
    session_key = _get_session_key(ctx, sender)

    text = _extract_text(msg)

    # Python logs for full traceability
    ctx.logger.info("📥 [wics] Incoming ChatMessage:")
    ctx.logger.info(f"   Sender: {sender}")
    ctx.logger.info(f"   Session: {chat_session}")
    ctx.logger.info(f"   Session key: {session_key}")
    ctx.logger.info(f"   Message ID: {incoming_msg_id}")
    ctx.logger.info(f"   Text content: {text}")

    if SENTRY_ENABLED:
        sentry_sdk.set_tag("agent_name", AGENT_NAME)
        sentry_sdk.set_tag("sender", sender)
        if chat_session is not None:
            sentry_sdk.set_tag("chat_session", str(chat_session))
        sentry_sdk.set_tag("session_key", session_key)
        if incoming_msg_id:
            sentry_sdk.set_tag("incoming_msg_id", incoming_msg_id)
        sentry_sdk.set_extra("text_length", len(text or ""))
    _sentry_breadcrumb("incoming_message", {"incoming_msg_id": incoming_msg_id, "text_length": len(text or "")})

    if not text:
        ctx.logger.warning("   ⚠️ Empty text content, skipping")
        return

    session = _get_session(ctx, sender)
    history = session.get("history", [])

    # Check if message contains an order ID (e.g. {"orderId":"123"}, {"order_id":"123"}, or just digits)
    order_id_match: str | None = None

    # Try JSON parse first
    try:
        parsed_json = json.loads(text)
        if isinstance(parsed_json, dict):
            for key in parsed_json.keys():
                if key.lower() in ["order_id", "orderid"]:
                    order_id_match = str(parsed_json[key]).strip()
                    break
    except Exception:
        pass

    # Regex fallback (handles messages like "@agent {...}" etc.)
    if not order_id_match:
        patterns = [
            r"['\"]order_id['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"['\"]orderId['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"order_id\s*[:=]\s*['\"]?([a-zA-Z0-9]+)['\"]?",
            r"orderId\s*[:=]\s*['\"]?([a-zA-Z0-9]+)['\"]?",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                order_id_match = m.group(1).strip()
                break

    # If message is just digits, treat as order id
    if not order_id_match:
        stripped = text.strip()
        if stripped.isdigit() and len(stripped) >= 8:
            order_id_match = stripped

    # If order id found, look up and respond with booking confirmation JSON (card payload)
    if order_id_match:
        ctx.logger.info(f"🔍 [wics] Detected order ID in message: {order_id_match}")
        _sentry_breadcrumb("order_lookup_detected", {"order_id": order_id_match})
        try:
            _sentry_breadcrumb("order_lookup_start", {"order_id": order_id_match})
            details = eventbrite_public.lookup_order(order_id_match)

            if details.get("error"):
                error_json = {
                    "order_id": order_id_match,
                    "error": details.get("error"),
                    "message": "Could not fetch order details",
                }
                outgoing = json.dumps(error_json, indent=2)
                outgoing_msg = ChatMessage(content=[TextContent(text=outgoing)], msg_id=uuid4())
                await ctx.send(sender, outgoing_msg)
                ctx.logger.info(
                    "📤 [wics] Sent order error JSON outgoing_msg_id=%s text=%s"
                    % (str(outgoing_msg.msg_id), _truncate_for_log(outgoing))
                )
                if SENTRY_ENABLED:
                    sentry_sdk.set_tag("outgoing_msg_id", str(outgoing_msg.msg_id))
                return

            costs = details.get("costs", {}) or {}
            attendees = details.get("attendees", []) or []
            ticket_types = [a.get("ticket_type") for a in attendees if isinstance(a, dict) and a.get("ticket_type")]

            # Add event details for dynamic booking card rendering
            event_info = {}
            try:
                event_info = eventbrite_public.get_event_info() or {}
            except Exception:
                event_info = {}
            venue = event_info.get("venue") if isinstance(event_info, dict) else None
            venue = venue if isinstance(venue, dict) else {}

            order_json = {
                "order_id": details.get("order_id") or order_id_match,
                "name": details.get("name"),
                "email": details.get("email"),
                "status": details.get("status"),
                "created": details.get("created"),
                "gross_cost": costs.get("gross_value"),
                "ticket_type": ticket_types[0] if ticket_types else None,
                "attendee_count": details.get("attendee_count", 0),
                "event_name": event_info.get("name") if isinstance(event_info, dict) else None,
                "venue_name": venue.get("name") if isinstance(venue, dict) else None,
                "venue_address": venue.get("address_display") if isinstance(venue, dict) else None,
                "event_start": event_info.get("start") if isinstance(event_info, dict) else None,
                "event_end": event_info.get("end") if isinstance(event_info, dict) else None,
                "timezone": event_info.get("timezone") if isinstance(event_info, dict) else None,
                "eventbrite_tickets_url": details.get("eventbrite_tickets_url"),
            }

            outgoing = json.dumps(order_json, indent=2)
            outgoing_msg = ChatMessage(content=[TextContent(text=outgoing)], msg_id=uuid4())
            await ctx.send(sender, outgoing_msg)
            ctx.logger.info(
                "📤 [wics] Sent order status JSON outgoing_msg_id=%s text=%s"
                % (str(outgoing_msg.msg_id), _truncate_for_log(outgoing))
            )
            _sentry_breadcrumb("order_lookup_ok", {"order_id": order_id_match})
            if SENTRY_ENABLED:
                sentry_sdk.set_tag("outgoing_msg_id", str(outgoing_msg.msg_id))
            return
        except Exception as e:
            ctx.logger.error(f"❌ [wics] Error looking up order {order_id_match}: {e}")
            _sentry_capture_exception(e, stage="order_lookup", data={"order_id": order_id_match})
            error_json = {"order_id": order_id_match, "error": "EXCEPTION", "message": str(e)}
            outgoing = json.dumps(error_json, indent=2)
            outgoing_msg = ChatMessage(content=[TextContent(text=outgoing)], msg_id=uuid4())
            await ctx.send(sender, outgoing_msg)
            if SENTRY_ENABLED:
                sentry_sdk.set_tag("outgoing_msg_id", str(outgoing_msg.msg_id))
            return

    try:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        reply, updated_history = openai_client.run_public_turn(text, history, model=model)

        session["history"] = updated_history[-20:]
        _save_session(ctx, sender, session)

        outgoing_msg = ChatMessage(content=[TextContent(text=reply)], msg_id=uuid4())
        try:
            await ctx.send(sender, outgoing_msg)
        except Exception as send_err:
            ctx.logger.error(f"❌ Failed to send reply: {send_err}")
            _sentry_capture_exception(send_err, stage="send_reply", data={"outgoing_msg_id": str(outgoing_msg.msg_id)})

        ctx.logger.info(
            "📤 [wics] Sent reply to sender=%s session=%s in_reply_to=%s outgoing_msg_id=%s text=%s"
            % (
                sender,
                str(chat_session) if chat_session else None,
                incoming_msg_id,
                str(outgoing_msg.msg_id),
                _truncate_for_log(reply),
            )
        )

        if SENTRY_ENABLED:
            sentry_sdk.set_tag("outgoing_msg_id", str(outgoing_msg.msg_id))

    except Exception as e:
        ctx.logger.error(f"Error in wics agent: {e}")
        _sentry_capture_exception(e, stage="openai_turn", data={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")})

        fallback = "Sorry — I’m having trouble right now. Please check the Eventbrite page for the latest details."
        outgoing_msg = ChatMessage(content=[TextContent(text=fallback)], msg_id=uuid4())
        try:
            await ctx.send(sender, outgoing_msg)
        except Exception as send_err:
            ctx.logger.error(f"❌ Failed to send error reply: {send_err}")
            _sentry_capture_exception(send_err, stage="send_error_reply", data={"outgoing_msg_id": str(outgoing_msg.msg_id)})


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"Ack from {sender[:12]}... for {msg.acknowledged_msg_id}")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()

