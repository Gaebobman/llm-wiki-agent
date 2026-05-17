from __future__ import annotations

import json
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


CRUD_ACTIONS = {"create", "read", "update", "delete"}
RISK_LEVELS = {"low", "medium", "high"}


@dataclass(frozen=True)
class QuerySection:
    terms: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    preferred_search: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryDecomposition:
    user_query: str
    intent: str
    requires_update: bool
    requires_approval: bool
    local_query: QuerySection
    global_query: QuerySection
    update_summary: str
    crud_action: str = "read"
    destructive_action: bool = False
    risk_level: str = "low"
    confidence: float = 0.0
    rationale: str = ""
    planner_source: str = "fallback"


def decompose_query(
    user_query: str,
    *,
    command_context: str = "read",
    planner_command: str | None = None,
    llm_base_url: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    planner_timeout_seconds: int = 30,
) -> QueryDecomposition:
    if planner_command:
        planned = _decompose_with_llm(
            user_query,
            command_context=command_context,
            planner_command=planner_command,
            timeout_seconds=planner_timeout_seconds,
        )
        if planned is not None:
            return planned
    if llm_base_url and llm_model:
        planned = _decompose_with_chat_api(
            user_query,
            command_context=command_context,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            timeout_seconds=planner_timeout_seconds,
        )
        if planned is not None:
            return planned
    return _fallback_decomposition(user_query, command_context=command_context)


def _decompose_with_llm(
    user_query: str,
    *,
    command_context: str,
    planner_command: str,
    timeout_seconds: int,
) -> QueryDecomposition | None:
    request = {
        "task": "classify_wiki_agent_request",
        "user_query": user_query,
        "command_context": command_context,
        "schema": {
            "crud_action": "create|read|update|delete",
            "intent": "short machine-readable intent",
            "destructive_action": "boolean",
            "risk_level": "low|medium|high",
            "requires_approval": "boolean",
            "local_query": {
                "terms": ["string"],
                "entities": ["string"],
                "themes": ["string"],
                "relations": ["string"],
            },
            "global_query": {
                "terms": ["string"],
                "entities": ["string"],
                "themes": ["string"],
                "relations": ["string"],
            },
            "update_summary": "one sentence summary",
            "confidence": "0.0-1.0",
            "rationale": "brief reason for classification",
        },
        "instructions": [
            "Use semantic context, not keyword matching.",
            "A negated destructive phrase is not destructive.",
            "Return strict JSON only.",
        ],
    }
    try:
        completed = subprocess.run(
            shlex.split(planner_command),
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    try:
        return _from_planner_payload(user_query, command_context, payload)
    except (TypeError, ValueError):
        return None


def _decompose_with_chat_api(
    user_query: str,
    *,
    command_context: str,
    llm_base_url: str,
    llm_model: str,
    llm_api_key: str | None,
    timeout_seconds: int,
) -> QueryDecomposition | None:
    payload = {
        "model": llm_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the semantic planner for a local wiki CRUD agent. "
                    "Classify the user's request by meaning, including negation and intent. "
                    "Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_query": user_query,
                        "command_context": command_context,
                        "required_schema": {
                            "crud_action": "create|read|update|delete",
                            "intent": "short machine-readable intent",
                            "destructive_action": "boolean",
                            "risk_level": "low|medium|high",
                            "requires_approval": "boolean",
                            "local_query": {
                                "terms": ["string"],
                                "entities": ["string"],
                                "themes": ["string"],
                                "relations": ["string"],
                            },
                            "global_query": {
                                "terms": ["string"],
                                "entities": ["string"],
                                "themes": ["string"],
                                "relations": ["string"],
                            },
                            "update_summary": "one sentence summary",
                            "confidence": "0.0-1.0",
                            "rationale": "brief reason for classification",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    url = f"{llm_base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
        planned = json.loads(content)
        result = _from_planner_payload(user_query, command_context, planned)
        return QueryDecomposition(**{**result.__dict__, "planner_source": "llm_api"})
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    try:
        return _from_planner_payload(user_query, command_context, payload)
    except (TypeError, ValueError):
        return None


def _from_planner_payload(
    user_query: str,
    command_context: str,
    payload: dict[str, Any],
) -> QueryDecomposition:
    crud_action = _safe_choice(str(payload.get("crud_action") or command_context), CRUD_ACTIONS, "read")
    risk_level = _safe_choice(str(payload.get("risk_level") or "low"), RISK_LEVELS, "low")
    destructive = _safe_bool(payload.get("destructive_action"), default=False)
    requires_update = crud_action in {"create", "update", "delete"} or command_context == "update"
    requires_approval = _safe_bool(
        payload.get("requires_approval"),
        default=requires_update or risk_level == "high",
    )
    if destructive:
        risk_level = "high"
        requires_approval = True

    local_payload = _as_dict(payload.get("local_query"))
    global_payload = _as_dict(payload.get("global_query"))
    return QueryDecomposition(
        user_query=user_query,
        intent=str(payload.get("intent") or _intent_for(crud_action)),
        requires_update=requires_update,
        requires_approval=requires_approval,
        local_query=_section_from_payload(local_payload, ["bm25", "keyword", "short_vector"], user_query),
        global_query=_section_from_payload(global_payload, ["semantic_vector", "hyde", "rerank"], user_query),
        update_summary=str(payload.get("update_summary") or user_query.strip()),
        crud_action=crud_action,
        destructive_action=destructive,
        risk_level=risk_level,
        confidence=_safe_float(payload.get("confidence"), default=0.0),
        rationale=str(payload.get("rationale") or ""),
        planner_source="llm",
    )


def _fallback_decomposition(user_query: str, *, command_context: str) -> QueryDecomposition:
    action = "update" if command_context == "update" else "read"
    terms = _extract_terms(user_query)
    requires_update = action in {"create", "update", "delete"}
    risk_level = "medium" if requires_update else "low"
    return QueryDecomposition(
        user_query=user_query,
        intent=_intent_for(action),
        requires_update=requires_update,
        requires_approval=requires_update,
        local_query=QuerySection(
            terms=terms[:12],
            entities=_file_or_identifier_terms(terms)[:8],
            preferred_search=["bm25", "keyword", "short_vector"],
        ),
        global_query=QuerySection(
            themes=terms[:12],
            preferred_search=["semantic_vector", "hyde", "rerank"],
        ),
        update_summary=user_query.strip().replace("\n", " "),
        crud_action=action,
        destructive_action=False,
        risk_level=risk_level,
        confidence=0.2,
        rationale="Conservative fallback based on command context; configure LLM_PLANNER_COMMAND for semantic planning.",
        planner_source="fallback",
    )


def _section_from_payload(
    payload: dict[str, Any],
    preferred_search: list[str],
    user_query: str,
) -> QuerySection:
    fallback_terms = _extract_terms(user_query)
    terms = _string_list(payload.get("terms")) or fallback_terms[:8]
    return QuerySection(
        terms=terms[:12],
        entities=_string_list(payload.get("entities"))[:8],
        themes=_string_list(payload.get("themes"))[:12],
        relations=_string_list(payload.get("relations"))[:8],
        preferred_search=preferred_search,
    )


def _extract_terms(text: str) -> list[str]:
    quoted = re.findall(r"[\"“](.+?)[\"”]", text)
    tokens = re.findall(r"[0-9A-Za-z가-힣_./+-]+", text)
    out: list[str] = []
    for item in quoted + tokens:
        value = item.strip()
        if value and value not in out:
            out.append(value)
    return out


def _file_or_identifier_terms(terms: list[str]) -> list[str]:
    out: list[str] = []
    for term in terms:
        if re.search(r"[0-9A-Z]", term) or "/" in term or "." in term or term.lower().endswith(
            ("doc", "docx", "pptx", "xlsx", "pdf", "md")
        ):
            out.append(term)
    return out or terms[:4]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_choice(value: str, allowed: set[str], default: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in allowed else default


def _safe_float(value: object, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _intent_for(action: str) -> str:
    if action == "read":
        return "answer_question"
    if action == "create":
        return "create_wiki_note"
    if action == "delete":
        return "delete_wiki_content"
    return "update_existing_page"
