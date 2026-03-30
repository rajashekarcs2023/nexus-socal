"""
OpenAI tool-calling loop for SoCal Claude Hackathon (public agent).

Luma-first for event details. Uses OpenAI hosted web search as fallback.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import OpenAI

from . import luma_public, faq_search

_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


SYSTEM_PROMPT = """You are the SoCal Claude Hackathon assistant — a helpful guide for participants.

**Primary rule:** Use the FAQ for accurate event details.

**Event basics:**
- Title: SoCal Claude Hackathon
- What: A one-day intercollegiate AI hackathon (100 students) for social impact, powered by Anthropic
- Hosts: UCLA, USC, Caltech, and Nexus
- Date: April 19, 2026, 8:30 AM – 6:30 PM
- Location: Grand Ackerman Ballroom, UCLA
- Price: Free (lunch and snacks provided)
- Registration: https://luma.com/dj0aohkq
- Application deadline: Friday, April 3rd (hard deadline Monday, April 6th)

**How to answer questions:**
1) If the user asks general event questions (when, where, who can participate, etc.) → call `get_event_faq_context` first.
2) If the user asks about registration details → call `get_event_info`.
3) If the user asks about submission requirements, judging, tracks, or technical details → call `get_event_faq_context`.
4) If the user expresses intent to register/sign up/apply → call `generate_booking_action` and return the JSON.
5) After the user completes registration, tell them: "Your registration has been submitted! This event requires organizer approval, so you'll receive a confirmation email from Luma once approved — it will include your event ticket and QR code for check-in."
6) If FAQ doesn't cover the question → suggest contacting the organizers.

**Style:**
- 2–5 sentences for most answers.
- Be clear and helpful.
- Don't invent details. If unknown, direct them to the event page or organizers.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_event_info",
            "description": "Get event details for the SoCal Claude Hackathon (date, location, hosts, registration link).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_faq_context",
            "description": "Get comprehensive FAQ content for the SoCal Claude Hackathon, including eligibility, timeline, requirements, resources, and contact info.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for details not covered by the FAQ or event info. Return a concise answer with sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_booking_action",
            "description": "Generate the registration action JSON when user wants to register / sign up. Use for intents like 'register', 'sign me up', 'how do I join'. Returns JSON with action and url pointing to the Luma registration page.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _web_search(query: str) -> Dict[str, Any]:
    client = get_openai_client()
    web_model = os.getenv("OPENAI_WEB_MODEL", "gpt-5").strip() or "gpt-5"

    allowed_domains = [
        "luma.com",
        "lu.ma",
        "fetch.ai",
        "innovationlab.fetch.ai",
        "www.instagram.com",
        "instagram.com",
        "www.linkedin.com",
        "linkedin.com",
    ]

    resp = client.responses.create(
        model=web_model,
        tools=[
            {
                "type": "web_search",
                "filters": {"allowed_domains": allowed_domains},
            }
        ],
        tool_choice="auto",
        include=["web_search_call.action.sources"],
        input=f"Answer the user's question concisely and cite sources.\n\nQuestion: {query}",
    )

    answer = getattr(resp, "output_text", "") or ""
    sources: list[dict[str, Any]] = []

    # Try to extract included sources from the response payload
    try:
        payload = resp.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            payload = resp.dict()  # type: ignore[call-arg]
        except Exception:
            payload = {}

    for item in (payload.get("output") or []):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        if isinstance(action, dict):
            srcs = action.get("sources") or []
            if isinstance(srcs, list):
                for s in srcs:
                    if isinstance(s, dict):
                        sources.append(
                            {
                                "url": s.get("url"),
                                "title": s.get("title"),
                                "type": s.get("type"),
                            }
                        )

    return {"query": query, "answer": answer, "sources": sources}


def _execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "get_event_info":
        return luma_public.get_event_info()
    if tool_name == "get_event_faq_context":
        return faq_search.get_event_faq_context()
    if tool_name == "web_search":
        q = (tool_args.get("query") or "").strip()
        if not q:
            return {"error": "QUERY_REQUIRED"}
        return _web_search(q)
    if tool_name == "generate_booking_action":
        reg = luma_public.get_registration_url()
        return {
            "action": "Click Here to book",
            "luma_url": reg["url"],
        }
    return {"error": "UNKNOWN_TOOL", "tool": tool_name}


def run_public_turn(
    user_message: str,
    history: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
) -> tuple[str, List[Dict[str, str]]]:
    """
    Run one agent turn with function-calling tools.
    """
    client = get_openai_client()

    recent_history = history[-10:] if len(history) > 10 else history

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(5):
        completion_params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": TOOLS,
        }
        if "gpt-5-nano" not in model.lower():
            completion_params["temperature"] = 0.2

        resp = client.chat.completions.create(**completion_params)
        choice = resp.choices[0]
        assistant_message = choice.message

        if not assistant_message.tool_calls:
            reply = assistant_message.content or "(no response)"
            updated = list(history)
            updated.append({"role": "user", "content": user_message})
            updated.append({"role": "assistant", "content": reply})
            return reply, updated

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in assistant_message.tool_calls
                ],
            }
        )

        for tc in assistant_message.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            result = _execute_tool(tool_name, args)

            # Return booking action directly to frontend (bypasses LLM)
            if tool_name == "generate_booking_action":
                updated = list(history)
                updated.append({"role": "user", "content": user_message})
                updated.append({"role": "assistant", "content": json.dumps(result)})
                return json.dumps(result), updated

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )

    fallback = "Sorry — I'm having trouble right now. Please try again or register directly at https://luma.com/dj0aohkq for the latest details."
    updated = list(history)
    updated.append({"role": "user", "content": user_message})
    updated.append({"role": "assistant", "content": fallback})
    return fallback, updated
