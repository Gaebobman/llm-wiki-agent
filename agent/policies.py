from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent.config import Settings
from agent.query_decomposer import QueryDecomposition


READ_COMMANDS = {
    "/status",
    "/queue",
    "/bases",
    "/local",
    "/global",
    "/search",
    "/route",
    "/patches",
    "/conflicts",
    "/logs",
}

WRITE_COMMANDS = {
    "/scan",
    "/ingest",
    "/update",
    "/apply",
    "/approve",
    "/reject",
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk_level: str
    approval_required: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandPolicyDecision:
    allowed: bool
    command: str
    access_level: str
    reasons: list[str] = field(default_factory=list)


def evaluate_command_policy(
    settings: Settings,
    command: str,
    user_id: int | None = None,
) -> CommandPolicyDecision:
    normalized = command.lower()
    if normalized in READ_COMMANDS:
        access_level = "read"
    elif normalized in WRITE_COMMANDS:
        access_level = "write"
    else:
        return CommandPolicyDecision(False, normalized, "unknown", ["unsupported command"])

    if settings.telegram_allowed_user_ids and user_id not in settings.telegram_allowed_user_ids:
        return CommandPolicyDecision(False, normalized, access_level, ["unauthorized user"])

    return CommandPolicyDecision(True, normalized, access_level, [f"{access_level} command"])


def evaluate_update_policy(
    settings: Settings,
    request_text: str,
    decomposition: QueryDecomposition,
    target_path: Path,
) -> PolicyDecision:
    reasons: list[str] = []
    try:
        ensure_wiki_markdown_target(settings, target_path)
    except ValueError as exc:
        return PolicyDecision(
            allowed=False,
            risk_level="blocked",
            approval_required=True,
            reasons=[str(exc)],
        )

    risk_level = _risk_level(request_text, decomposition)
    reasons.append("wiki markdown target")
    if risk_level == "high":
        reasons.append("planner marked high-risk mutation")
    elif risk_level == "medium":
        reasons.append("content mutation")
    else:
        reasons.append("low-risk proposal")

    return PolicyDecision(
        allowed=True,
        risk_level=risk_level,
        approval_required=True,
        reasons=reasons,
    )


def requires_second_approval(risk_level: str) -> bool:
    return risk_level == "high"


def validate_patch_record_schema(record: object) -> None:
    required = {
        "patch_id": str,
        "request_text": str,
        "target_file": str,
        "base_sha256": str,
        "new_sha256": str,
        "status": str,
        "approval_required": bool,
        "risk_level": str,
        "created_at": str,
        "updated_at": str,
        "query": str,
        "summary": str,
        "evidence_paths": list,
        "diff_path": str,
        "before_path": str,
        "after_path": str,
        "decomposition": dict,
    }
    for name, expected_type in required.items():
        value = getattr(record, name, None)
        if not isinstance(value, expected_type):
            raise ValueError(f"invalid patch metadata field: {name}")
    if record.status not in {"pending", "approved", "applied", "rejected"}:
        raise ValueError(f"invalid patch status: {record.status}")
    if record.risk_level not in {"low", "medium", "high", "blocked"}:
        raise ValueError(f"invalid patch risk level: {record.risk_level}")
    for name in ("base_sha256", "new_sha256"):
        value = getattr(record, name)
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"invalid patch hash field: {name}")


def ensure_wiki_markdown_target(settings: Settings, target_path: Path) -> Path:
    wiki_root = settings.wiki_root.resolve()
    resolved = target_path.resolve()
    if not _is_relative_to(resolved, wiki_root):
        raise ValueError(f"target is outside wiki root: {target_path}")
    rel = resolved.relative_to(wiki_root)
    if not rel.parts:
        raise ValueError("target cannot be wiki root")
    if rel.parts[0] != "wiki":
        raise ValueError(f"target must be under wiki/: {rel}")
    if "raw" in rel.parts:
        raise ValueError(f"target cannot be under raw/: {rel}")
    if resolved.suffix.lower() != ".md":
        raise ValueError(f"target must be markdown: {rel}")
    return resolved


def _risk_level(request_text: str, decomposition: QueryDecomposition) -> str:
    if decomposition.destructive_action or decomposition.risk_level == "high":
        return "high"
    if decomposition.requires_update or decomposition.risk_level == "medium":
        return "medium"
    return "low"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
