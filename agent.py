"""
SoCal Claude Hackathon — Public agent.

Luma-based event helper with OpenAI web search fallback.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import sentry_sdk
from dotenv import load_dotenv
from pydantic import BaseModel
from uagents import Agent, Context, Model, Protocol
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

from tools import openai_client, luma_public  # noqa: E402

# Config
AGENT_NAME = os.getenv("AGENT_NAME", "SOCAL_NEXUS")
AGENT_SEED = os.getenv("AGENT_SEED", "socal_claude_hackathon_public_agent")
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

# Signup notification message model
class SignupNotification(Model):
    """Message sent to admin agent when someone registers."""
    order_id: str
    email: str
    name: str
    timestamp: str
    event_name: str = "SoCal Claude Hackathon"

# Admin agent address for signup tracking
ADMIN_AGENT_ADDRESS = os.getenv("ADMIN_AGENT_ADDRESS", "").strip()

SESSIONS_KEY = "socal_sessions"


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


def _parse_luma_confirmation(text: str) -> dict | None:
    """Detect a Luma registration confirmation callback from the frontend.

    Expected format (sent after user registers via the Luma overlay):
        {"luma_event_id":"evt-xxx","status":"request_submitted","registered_email":"u@e.com"}
    """
    for candidate in (text, text.split("}", 1)[0] + "}" if "{" in text else ""):
        start = candidate.find("{")
        if start == -1:
            continue
        try:
            data = json.loads(candidate[start:])
            if isinstance(data, dict) and "luma_event_id" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


POST_REGISTRATION_MESSAGE = (
    'If you completed your registration, you should receive an email titled '
    '**"Registration Pending Approval for SoCal Claude Hackathon"** from Luma shortly. '
    "This event requires organizer approval \u2014 once approved, you'll get a follow-up "
    "email with your **event ticket and QR code** for check-in.\n\n"
    "If you didn't receive this email, you may not have completed the registration. "
    'Just say **"register"** and I\'ll bring up the registration card again!\n\n'
    "Feel free to ask me any questions about the hackathon!"
)


@agent.on_event("startup")
async def on_startup(ctx: Context):
    ctx.logger.info(f"🎓 {AGENT_NAME} started. Address: {agent.wallet.address()}")
    if SENTRY_ENABLED:
        ctx.logger.info(f"🛰️  Sentry enabled (env={SENTRY_ENVIRONMENT})")

    ctx.logger.info(f"✅ Luma event: {os.getenv('LUMA_EVENT_ID', 'N/A')} → {os.getenv('LUMA_EVENT_URL', 'N/A')}")


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    
    user_text = _extract_text(msg)
    ctx.logger.info(f"📩 Message from {sender[:10]}...: {_truncate_for_log(user_text)}")
    
    if not user_text:
        ctx.logger.warning("Empty message, skipping")
        return
    
    _sentry_breadcrumb("handle_chat_start", {"sender": sender, "msg_len": len(user_text)})
    
    # Check for Luma registration confirmation callback from frontend
    confirmation = _parse_luma_confirmation(user_text)
    if confirmation:
        ctx.logger.info(
            f"\u2705 Luma confirmation received: event={confirmation.get('luma_event_id')} "
            f"status={confirmation.get('status')}"
        )
        # Try to verify registration via Luma API using the callback email
        reply_msg = POST_REGISTRATION_MESSAGE
        cb_email = (confirmation.get("registered_email") or "").strip()
        if cb_email:
            try:
                guest = luma_public.check_guest_status(cb_email)
                if guest.get("found"):
                    approval = guest.get("approval_status", "")
                    name = guest.get("guest_name") or ""
                    greeting = f"{name}, your" if name else "Your"
                    if approval == "approved":
                        reply_msg = (
                            f"{greeting} registration is **approved**! "
                            "You can find your QR code for check-in in the confirmation email from Luma.\n\n"
                            "Feel free to ask me any questions about the hackathon!"
                        )
                    else:
                        reply_msg = (
                            f"{greeting} registration has been submitted and is **pending organizer approval**. "
                            "Once approved, you'll receive a follow-up email from Luma with your event ticket "
                            "and QR code for check-in.\n\n"
                            "Meanwhile, feel free to ask me any questions about the hackathon!"
                        )
                    ctx.logger.info(f"✅ Luma API confirmed registration for {cb_email}: {approval}")
            except Exception as exc:
                ctx.logger.warning(f"⚠️ Luma API check failed, using fallback message: {exc}")
        await ctx.send(
            sender,
            ChatMessage(content=[TextContent(text=reply_msg)], msg_id=uuid4()),
        )
        _sentry_breadcrumb("luma_confirmation_handled")
        return
    
    # Chat flow
    session = _get_session(ctx, sender)
    
    try:
        # Call OpenAI with tools
        reply_text, updated_history = openai_client.run_public_turn(
            user_message=user_text,
            history=session["history"],
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
        
        ctx.logger.info(f"✅ Reply: {_truncate_for_log(reply_text)}")
        session["history"] = updated_history[-20:]
        _save_session(ctx, sender, session)
        
        # Send reply
        await ctx.send(
            sender,
            ChatMessage(content=[TextContent(text=reply_text)], msg_id=uuid4()),
        )
        _sentry_breadcrumb("handle_chat_ok")
        
    except Exception as e:
        ctx.logger.error(f"Error handling chat: {e}")
        _sentry_capture_exception(e, stage="handle_chat", data={"sender": sender})
        
        await ctx.send(
            sender,
            ChatMessage(
                content=[TextContent(text="Sorry, I encountered an error. Please try again.")],
                msg_id=uuid4(),
            ),
        )


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    # Empty handler for testing - just log that ack was received
    ctx.logger.info(f"📥 [TEST] Received ChatAcknowledgement from {sender}")
    pass

agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()

