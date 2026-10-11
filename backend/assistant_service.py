"""Read-only conversational assistant orchestration and PostgreSQL history."""

import json
import re
import secrets
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select

from ai_provider import AIProvider, AIProviderError, OllamaProvider
from assistant_tools import TOOL_SCHEMAS, call_tool
from database import AssistantConversation, AssistantMessage, session_scope


SYSTEM_PROMPT = """You are the ShortsFlow AI assistant. Answer naturally and concisely.
You can answer questions about this ShortsFlow workspace only using the provided read-only tools.
Never claim workspace-specific facts without tool results. Never reveal credentials, tokens,
database details, environment variables, raw SQL, or private implementation data. You cannot
change settings, generate drafts, upload, schedule, or delete anything. For planning requests,
read relevant settings and existing videos before suggesting ideas."""


def _conversation(session_id: str | None) -> AssistantConversation:
    with session_scope() as session:
        if session_id:
            record = session.scalar(select(AssistantConversation).where(AssistantConversation.session_id == session_id))
            if record:
                return record
        record = AssistantConversation(session_id=secrets.token_urlsafe(18))
        session.add(record)
        session.flush()
        return record


def _append_message(conversation_id: int, role: str, content: str, tools_used: list[str] | None = None) -> None:
    with session_scope() as session:
        session.add(AssistantMessage(conversation_id=conversation_id, role=role, content=content, tools_used=tools_used or []))


def get_history(session_id: str) -> list[dict[str, object]]:
    with session_scope() as session:
        conversation = session.scalar(select(AssistantConversation).where(AssistantConversation.session_id == session_id))
        if not conversation:
            return []
        messages = session.scalars(select(AssistantMessage).where(AssistantMessage.conversation_id == conversation.id).order_by(AssistantMessage.id)).all()
        return [{"role": message.role, "content": message.content, "tools_used": message.tools_used, "created_at": message.created_at.isoformat()} for message in messages]


def clear_history(session_id: str) -> None:
    with session_scope() as session:
        conversation = session.scalar(select(AssistantConversation).where(AssistantConversation.session_id == session_id))
        if conversation:
            session.execute(delete(AssistantMessage).where(AssistantMessage.conversation_id == conversation.id))


def _fallback_tools(message: str) -> list[tuple[str, dict[str, object]]]:
    text = message.casefold()
    calls: list[tuple[str, dict[str, object]]] = []
    if (re.search(r"how many videos|channel videos|subscribers|total views", text)
            and "videos per day" not in text): calls.append(("get_channel_stats", {}))
    if "settings" in text or "configured" in text or "videos per day" in text: calls.append(("get_settings", {}))
    if "upload schedule" in text or "upload time" in text: calls.append(("get_upload_schedule", {}))
    if "latest generated draft" in text or "latest draft" in text: calls.append(("get_latest_draft", {}))
    if "recent" in text and ("video" in text or "upload" in text): calls.append(("get_recent_videos", {"limit": 5}))
    if re.search(r"already made|have i made|duplicate|about ", text):
        query = re.sub(r".*?(?:about|made)\s+", "", message, flags=re.IGNORECASE).strip(" ?.") or message
        calls.extend([("search_existing_videos", {"query": query}), ("check_duplicate", {"query": query})])
    if "plan" in text or "suggest" in text: calls.extend([("get_settings", {}), ("get_recent_videos", {"limit": 10}), ("get_latest_draft", {})])
    unique: list[tuple[str, dict[str, object]]] = []
    for call in calls:
        if call not in unique: unique.append(call)
    return unique


def _tool_calls_from_response(response: dict[str, Any]) -> list[tuple[str, dict[str, object]]]:
    calls = response.get("message", {}).get("tool_calls", [])
    parsed: list[tuple[str, dict[str, object]]] = []
    for call in calls if isinstance(calls, list) else []:
        function = call.get("function", {}) if isinstance(call, dict) else {}
        name = function.get("name")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try: arguments = json.loads(arguments)
            except json.JSONDecodeError: arguments = {}
        if isinstance(name, str) and isinstance(arguments, dict): parsed.append((name, arguments))
    return parsed


def _run_tools(calls: Sequence[tuple[str, dict[str, object]]]) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    names: list[str] = []
    for name, arguments in calls:
        if name in names: continue
        try:
            results.append({"tool": name, "result": call_tool(name, arguments)})
        except (ValueError, TypeError) as error:
            results.append({"tool": name, "result": {"error": str(error)}})
        names.append(name)
    return results, names


def chat(message: str, session_id: str | None = None, provider: AIProvider | None = None) -> dict[str, object]:
    conversation = _conversation(session_id)
    prior = get_history(conversation.session_id)[-12:]
    provider_messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    provider_messages.extend({"role": str(item["role"]), "content": str(item["content"])} for item in prior)
    provider_messages.append({"role": "user", "content": message})
    ai_provider = provider or OllamaProvider()
    _append_message(conversation.id, "user", message)
    first_response = ai_provider.chat(provider_messages, TOOL_SCHEMAS)
    calls = _tool_calls_from_response(first_response) or _fallback_tools(message)
    tool_results, tools_used = _run_tools(calls)
    if tool_results:
        provider_messages.append({"role": "assistant", "content": first_response.get("message", {}).get("content", "")})
        provider_messages.append({"role": "tool", "content": json.dumps(tool_results, ensure_ascii=False)})
        final_response = ai_provider.chat(provider_messages)
        answer = str(final_response.get("message", {}).get("content", "")).strip()
    else:
        answer = str(first_response.get("message", {}).get("content", "")).strip()
    if not answer:
        answer = "I couldn't form a response from the local model. Please try again."
    _append_message(conversation.id, "assistant", answer, tools_used)
    return {"session_id": conversation.session_id, "response": answer, "tools_used": tools_used, "tool_results": tool_results}
