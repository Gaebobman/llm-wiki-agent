from __future__ import annotations

from pathlib import Path

from agent.config import Settings
from agent.file_utils import is_probably_text, relative_to_root, safe_stem
from agent.timeutils import today


def source_note_path(settings: Settings, raw_rel_path: str) -> Path:
    return settings.wiki_sources_dir / f"{safe_stem(Path(raw_rel_path))}.md"


def build_source_note(settings: Settings, raw_rel_path: str, sha256: str, ingest_source: str) -> str:
    raw_path = settings.wiki_root / raw_rel_path
    title = Path(raw_rel_path).stem.replace("-", " ").replace("_", " ").strip() or Path(raw_rel_path).name
    content = _extract_body(raw_path)
    date = today()
    return "\n".join(
        [
            "---",
            f"title: {title}",
            "type: source",
            "status: active",
            f"created: {date}",
            f"updated: {date}",
            "source_files:",
            f"  - {raw_rel_path}",
            f"ingest_source: {ingest_source}",
            f"source_hash: {sha256}",
            "retrieval_scope: local",
            "review_state: draft",
            "evidence_level: parsed",
            "---",
            "",
            f"# {title}",
            "",
            "## Source",
            "",
            f"- Raw file: `{raw_rel_path}`",
            f"- SHA256: `{sha256}`",
            f"- Ingest source: `{ingest_source}`",
            "",
            "## Extracted Content",
            "",
            content,
            "",
        ]
    )


def write_source_note(settings: Settings, raw_rel_path: str, sha256: str, ingest_source: str) -> Path:
    note_path = source_note_path(settings, raw_rel_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        build_source_note(settings, raw_rel_path, sha256, ingest_source),
        encoding="utf-8",
    )
    return note_path


def append_index_entry(settings: Settings, note_path: Path, raw_rel_path: str) -> None:
    settings.wiki_index_path.parent.mkdir(parents=True, exist_ok=True)
    rel_note = relative_to_root(note_path, settings.wiki_root)
    entry = f"- [[{rel_note.removesuffix('.md')}]] from `{raw_rel_path}`"
    if settings.wiki_index_path.exists():
        existing = settings.wiki_index_path.read_text(encoding="utf-8")
    else:
        existing = "# Wiki Index\n\n## Sources\n\n"
    if entry in existing:
        return
    if "## Sources" not in existing:
        existing = existing.rstrip() + "\n\n## Sources\n\n"
    settings.wiki_index_path.write_text(existing.rstrip() + "\n" + entry + "\n", encoding="utf-8")


def append_log_entry(settings: Settings, raw_rel_path: str, note_path: Path, sha256: str, source: str) -> None:
    settings.wiki_log_path.parent.mkdir(parents=True, exist_ok=True)
    rel_note = relative_to_root(note_path, settings.wiki_root)
    date_heading = f"## {today()}"
    if settings.wiki_log_path.exists():
        existing = settings.wiki_log_path.read_text(encoding="utf-8")
    else:
        existing = "# Wiki Log\n\n"
    entry = "\n".join(
        [
            f"- Ingested `{raw_rel_path}`",
            f"  - Created `{rel_note}`",
            f"  - Source: {source}",
            f"  - Hash: `{sha256}`",
            "  - qmd index refresh requested",
        ]
    )
    if entry in existing:
        return
    if date_heading not in existing:
        existing = existing.rstrip() + f"\n\n{date_heading}\n\n"
    settings.wiki_log_path.write_text(existing.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def _extract_body(raw_path: Path) -> str:
    if not raw_path.exists():
        return "_Raw source file is missing at ingest time._"
    if not is_probably_text(raw_path):
        return (
            "_Binary document extraction is pending. The raw file has been registered "
            "as a source note for later parser expansion._"
        )
    try:
        text = raw_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = raw_path.read_text(encoding="utf-8", errors="replace")
    if raw_path.suffix.lower() in {".md", ".markdown"}:
        return text.strip() or "_No text content extracted._"
    suffix = raw_path.suffix.lower().lstrip(".") or "text"
    return f"```{suffix}\n{text.rstrip()}\n```"
