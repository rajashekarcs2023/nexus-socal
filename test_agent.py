"""
Test agent to send messages to Stanford WiCS agent
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

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

# Config

AGENTVERSE_URL = os.getenv("AGENTVERSE_URL", "https://agentverse.ai")

# Target agent address (Stanford WiCS agent)
TARGET_AGENT_ADDRESS = os.getenv("TARGET_AGENT_ADDRESS", "agent1qvc3w0z964pnww9y03ktgkh35u6g68zph26kz3vrfng38swxxwmvcsl4z62")

# Create test agent
test_agent = Agent(
    name="raj1testing",
    seed="raj1testingstanford",
    port=8005,
    mailbox=True
)

chat_proto = Protocol(spec=chat_protocol_spec)

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"✅ Got acknowledgement from {sender[:12]}... for message {msg.acknowledged_msg_id}")

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"📨 Got message from {sender[:12]}...")
    for item in msg.content or []:
        if isinstance(item, TextContent):
            ctx.logger.info(f"   Content: {item.text}")
    
    # Send acknowledgement
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.utcnow(),
        acknowledged_msg_id=msg.msg_id
    ))

# Send test message to Stanford WiCS agent after startup
async def send_test_message(ctx: Context):
    """Send a test message to Stanford WiCS agent"""
    ctx.logger.info(f"📤 Sending test message to {TARGET_AGENT_ADDRESS}")
    
    test_message = ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text="Hello! This is a test message from test agent. What time does the Stanford Women in CS: CONNECT event start?")]
    )
    
    try:
        await ctx.send(TARGET_AGENT_ADDRESS, test_message)
        ctx.logger.info("✅ Test message sent successfully")
    except Exception as e:
        ctx.logger.error(f"❌ Failed to send test message: {e}")

@test_agent.on_event("startup")
async def on_startup(ctx: Context):
    ctx.logger.info("🧪 Test Agent started successfully")
    # Wait a moment for agent to be ready, then send test message
    import asyncio
    await asyncio.sleep(5)  # Wait 5 seconds
    await send_test_message(ctx)

test_agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    print(f"🧪 Test Agent Starting...")
    print(f"   Target: {TARGET_AGENT_ADDRESS}")
    print(f"   AgentVerse: {AGENTVERSE_URL}")
    print(f"\n📤 Will send test messages to Stanford WiCS agent...")
    test_agent.run()
