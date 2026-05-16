from __future__ import annotations

from pathlib import Path

from agent.config import Settings
from agent.timeutils import today


def build_update_document(
    settings: Settings,
    target_path: Path,
    request_text: str,
    evidence_lines: list[str],
    create_new: bool = False,
) -> str:
    title = target_path.stem.replace("-", " ").replace("_", " ").strip() or target_path.stem
    base = _read_existing(target_path) if target_path.exists() and not create_new else ""
    if create_new or not base.strip():
        base = _frontmatter(title=title, target_rel=str(target_path.relative_to(settings.wiki_root)))
        base += f"# {title}\n\n"
    section = _render_update_section(request_text, evidence_lines)
    if section in base:
        return base
    return base.rstrip() + "\n\n" + section + "\n"


def write_document(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_index_if_needed(settings: Settings, target_path: Path) -> None:
    if target_path.exists():
        from agent.wiki_writer import append_index_entry

        append_index_entry(settings, target_path, str(target_path.relative_to(settings.wiki_root)))


def append_log(
    settings: Settings,
    target_path: Path,
    request_text: str,
    patch_id: str,
    action: str,
) -> None:
    settings.wiki_log_path.parent.mkdir(parents=True, exist_ok=True)
    date_heading = f"## {today()}"
    rel_target = str(target_path.relative_to(settings.wiki_root))
    if settings.wiki_log_path.exists():
        existing = settings.wiki_log_path.read_text(encoding="utf-8")
    else:
        existing = "# Wiki Log\n\n"
    entry = "\n".join(
        [
            f"- {action}: `{rel_target}`",
            f"  - Patch: `{patch_id}`",
            f"  - Request: {request_text}",
        ]
    )
    if entry in existing:
        return
    if date_heading not in existing:
        existing = existing.rstrip() + f"\n\n{date_heading}\n\n"
    settings.wiki_log_path.write_text(existing.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def _render_update_section(request_text: str, evidence_lines: list[str]) -> str:
    lines = [
        f"## Update Proposal - {today()}",
        "",
        f"- Request: {request_text}",
    ]
    if evidence_lines:
        lines.append("- Evidence:")
        for line in evidence_lines:
            lines.append(f"  - {line}")
    return "\n".join(lines)


def _frontmatter(title: str, target_rel: str) -> str:
    return "\n".join(
        [
            "---",
            f"title: {title}",
            "type: topic",
            "status: draft",
            f"created: {today()}",
            f"updated: {today()}",
            "review_state: draft",
            "source_files: []",
            f"target_path: {target_rel}",
            "---",
            "",
        ]
    )


def _read_existing(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
