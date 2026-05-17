from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from agent.config import Settings
from agent.evidence_retriever import EvidenceBundle, retrieve_evidence
from agent.policies import (
    ensure_wiki_markdown_target,
    evaluate_update_policy,
    requires_second_approval,
    validate_patch_record_schema,
)
from agent.query_decomposer import QueryDecomposition, decompose_query
from agent.timeutils import now_iso
from agent.wiki_updater import append_index_if_needed, append_log, build_update_document, write_document


@dataclass(frozen=True)
class PatchRecord:
    patch_id: str
    request_text: str
    target_file: str
    base_sha256: str
    new_sha256: str
    status: str
    approval_required: bool
    risk_level: str
    created_at: str
    updated_at: str
    query: str
    summary: str
    evidence_paths: list[str]
    diff_path: str
    before_path: str
    after_path: str
    decomposition: dict


@dataclass(frozen=True)
class PatchBuildResult:
    record: PatchRecord
    before_text: str
    after_text: str


def patches_dir(settings: Settings) -> Path:
    return settings.patches_dir


def create_patch_for_update(
    settings: Settings,
    request_text: str,
    route_result: dict | None = None,
    evidence_bundle: EvidenceBundle | None = None,
    decomposition: QueryDecomposition | None = None,
) -> PatchBuildResult:
    decomposition = decomposition or decompose_query(
        request_text,
        command_context="update",
        planner_command=settings.llm_planner_command,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        llm_api_key=settings.llm_api_key,
        planner_timeout_seconds=settings.llm_planner_timeout_seconds,
    )
    route_result = route_result or {}
    evidence_bundle = evidence_bundle or retrieve_evidence(settings, request_text, route_result=route_result)
    target_path = _pick_target_path(settings, decomposition, route_result, evidence_bundle)
    target_path = ensure_wiki_markdown_target(settings, target_path)
    policy = evaluate_update_policy(settings, request_text, decomposition, target_path)
    if not policy.allowed:
        raise ValueError("; ".join(policy.reasons) or "policy denied update")
    before_text = _read_text(target_path) if target_path.exists() else ""
    after_text = build_update_document(
        settings,
        target_path,
        request_text=request_text,
        evidence_lines=[item.excerpt or item.path for item in evidence_bundle.items],
        create_new=not target_path.exists(),
    )
    patch_id = _new_patch_id(request_text)
    patch_dir = patches_dir(settings) / patch_id
    patch_dir.mkdir(parents=True, exist_ok=True)
    before_path = patch_dir / "before.md"
    after_path = patch_dir / "after.md"
    diff_path = patch_dir / "diff.patch"
    meta_path = patch_dir / "metadata.json"
    before_path.write_text(before_text, encoding="utf-8")
    after_path.write_text(after_text, encoding="utf-8")
    diff_text = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=str(target_path),
            tofile=str(target_path),
            lineterm="",
        )
    )
    diff_path.write_text(diff_text + ("\n" if diff_text else ""), encoding="utf-8")
    record = PatchRecord(
        patch_id=patch_id,
        request_text=request_text,
        target_file=str(target_path.relative_to(settings.wiki_root)),
        base_sha256=_sha256(before_text),
        new_sha256=_sha256(after_text),
        status="pending",
        approval_required=policy.approval_required,
        risk_level=policy.risk_level,
        created_at=now_iso(),
        updated_at=now_iso(),
        query=decomposition.user_query,
        summary=evidence_bundle.summary,
        evidence_paths=[item.path for item in evidence_bundle.items],
        diff_path=str(diff_path),
        before_path=str(before_path),
        after_path=str(after_path),
        decomposition=asdict(decomposition),
    )
    meta_path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
    _append_patch_log(settings, f"created {patch_id} target={record.target_file} risk={record.risk_level}")
    return PatchBuildResult(record=record, before_text=before_text, after_text=after_text)


def apply_patch(settings: Settings, patch_id: str) -> PatchRecord:
    record = load_patch(settings, patch_id)
    if requires_second_approval(record.risk_level) and record.status != "approved":
        raise ValueError(f"high-risk patch requires /approve before apply: {patch_id}")
    if not requires_second_approval(record.risk_level) and record.status != "pending":
        raise ValueError(f"patch is not pending: {patch_id}")
    if record.status not in {"pending", "approved"}:
        raise ValueError(f"patch is not applicable: {patch_id}")
    patch_dir = patches_dir(settings) / patch_id
    after_path = patch_dir / "after.md"
    target_path = settings.wiki_root / record.target_file
    target_path = ensure_wiki_markdown_target(settings, target_path)
    content = after_path.read_text(encoding="utf-8")
    _validate_patch_files(record, patch_dir, content)
    current = _read_text(target_path) if target_path.exists() else ""
    if _sha256(current) != record.base_sha256:
        raise ValueError(f"patch base mismatch for {patch_id}")
    write_document(target_path, content)
    append_index_if_needed(settings, target_path)
    append_log(settings, target_path, record.request_text, patch_id, "patch_apply")
    updated = _replace_record_status(settings, patch_id, "applied")
    _append_patch_log(settings, f"applied {patch_id} target={record.target_file}")
    return updated


def approve_patch(settings: Settings, patch_id: str) -> PatchRecord:
    record = load_patch(settings, patch_id)
    if record.status != "pending":
        raise ValueError(f"patch is not pending: {patch_id}")
    if not requires_second_approval(record.risk_level):
        raise ValueError(f"patch does not require second approval: {patch_id}")
    updated = _replace_record_status(settings, patch_id, "approved")
    _append_patch_log(settings, f"approved {patch_id} target={record.target_file}")
    return updated


def reject_patch(settings: Settings, patch_id: str) -> PatchRecord:
    record = load_patch(settings, patch_id)
    if record.status not in {"pending", "approved", "applied"}:
        raise ValueError(f"patch is not rejectable: {patch_id}")
    updated = _replace_record_status(settings, patch_id, "rejected")
    _append_patch_log(settings, f"rejected {patch_id} target={record.target_file}")
    return updated


def load_patch(settings: Settings, patch_id: str) -> PatchRecord:
    meta_path = patches_dir(settings) / patch_id / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    record = PatchRecord(**data)
    validate_patch_record_schema(record)
    return record


def list_patches(settings: Settings, status: str | None = None) -> list[PatchRecord]:
    out: list[PatchRecord] = []
    root = patches_dir(settings)
    if not root.exists():
        return out
    for meta_path in sorted(root.glob("*/metadata.json")):
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        record = PatchRecord(**data)
        if status and record.status != status:
            continue
        out.append(record)
    return out


def list_conflicts(settings: Settings) -> list[PatchRecord]:
    conflicts: list[PatchRecord] = []
    for record in [item for item in list_patches(settings) if item.status in {"pending", "approved"}]:
        target_path = settings.wiki_root / record.target_file
        current = _read_text(target_path) if target_path.exists() else ""
        if _sha256(current) != record.base_sha256:
            conflicts.append(record)
    return conflicts


def recent_logs(settings: Settings, limit: int = 20) -> list[str]:
    logs_dir = settings.logs_dir
    if not logs_dir.exists():
        return []
    candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for path in candidates[:5]:
        lines.extend(_tail_lines(path, limit))
        if len(lines) >= limit:
            break
    return lines[:limit]


def build_patch_message(record: PatchRecord) -> str:
    lines = [
        "[승인 필요]",
        f"Patch: {record.patch_id}",
        f"대상: {record.target_file}",
        f"Risk: {record.risk_level}",
        f"Approval required: {record.approval_required}",
        "",
        "변경 요약:",
        f"- {record.summary or record.request_text}",
        "",
        "적용하려면:",
    ]
    if requires_second_approval(record.risk_level):
        lines.append(f"/approve {record.patch_id}")
    lines.extend(
        [
            f"/apply {record.patch_id}",
            "",
            "거절하려면:",
            f"/reject {record.patch_id}",
        ]
    )
    return "\n".join(lines)


def format_patch_list(patches: list[PatchRecord]) -> str:
    lines = ["[Patch 목록]"]
    if not patches:
        return "\n".join(lines + ["없음"])
    for record in patches:
        lines.append(
            f"- {record.patch_id} | {record.status} | {record.target_file} | {record.risk_level}"
        )
    return "\n".join(lines)


def format_conflicts(conflicts: list[PatchRecord]) -> str:
    lines = ["[충돌]"]
    if not conflicts:
        return "\n".join(lines + ["없음"])
    for record in conflicts:
        lines.append(f"- {record.patch_id} | {record.target_file}")
    return "\n".join(lines)


def _replace_record_status(settings: Settings, patch_id: str, status: str) -> PatchRecord:
    record = load_patch(settings, patch_id)
    updated = PatchRecord(**{**asdict(record), "status": status, "updated_at": now_iso()})
    validate_patch_record_schema(updated)
    meta_path = patches_dir(settings) / patch_id / "metadata.json"
    meta_path.write_text(json.dumps(asdict(updated), ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def _validate_patch_files(record: PatchRecord, patch_dir: Path, after_text: str) -> None:
    before_path = Path(record.before_path)
    after_path = Path(record.after_path)
    diff_path = Path(record.diff_path)
    for path in (before_path, after_path, diff_path):
        if not _is_relative_to(path.resolve(), patch_dir.resolve()):
            raise ValueError(f"patch file path escapes patch directory: {path}")
        if not path.exists() or not path.is_file():
            raise ValueError(f"missing patch file: {path}")
    before_text = before_path.read_text(encoding="utf-8")
    if _sha256(before_text) != record.base_sha256:
        raise ValueError(f"patch before hash mismatch: {record.patch_id}")
    if _sha256(after_text) != record.new_sha256:
        raise ValueError(f"patch after hash mismatch: {record.patch_id}")


def _pick_target_path(
    settings: Settings,
    decomposition: QueryDecomposition,
    route_result: dict,
    evidence_bundle: EvidenceBundle,
) -> Path:
    for candidate in route_result.get("anchors", []) if route_result else []:
        rel = str(candidate.get("path") or "")
        if rel:
            return settings.wiki_root / rel
    for item in evidence_bundle.items:
        if item.path.startswith("wiki/"):
            return settings.wiki_root / item.path
    slug = _slugify(decomposition.user_query)
    return settings.wiki_root / "wiki" / "topics" / f"{slug}.md"


def _new_patch_id(request_text: str) -> str:
    digest = hashlib.sha1(request_text.encode("utf-8")).hexdigest()[:8]
    return f"patch_{now_iso().replace('-', '').replace(':', '').replace('+', '_')}_{digest}"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text.lower()).strip("-")
    return slug[:60] or "update-request"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tail_lines(path: Path, limit: int) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def _append_patch_log(settings: Settings, message: str) -> None:
    log_path = settings.logs_dir / "patch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} {message}"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
