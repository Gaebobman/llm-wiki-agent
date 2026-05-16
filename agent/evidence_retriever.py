from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agent.config import Settings
from agent.file_utils import relative_to_root


@dataclass(frozen=True)
class EvidenceItem:
    path: str
    score: int
    kind: str
    excerpt: str
    source_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceBundle:
    query: str
    items: list[EvidenceItem]
    source_paths: list[str]
    summary: str


def retrieve_evidence(
    settings: Settings,
    query: str,
    route_result: dict | None = None,
    limit: int = 5,
) -> EvidenceBundle:
    candidate_paths = _candidate_paths(settings, query, route_result, limit=limit)
    items: list[EvidenceItem] = []
    seen: set[str] = set()
    for path in candidate_paths:
        rel = _to_relative(settings, path)
        if rel in seen:
            continue
        seen.add(rel)
        text = _read_text(path)
        if text is None:
            continue
        frontmatter, body = _split_frontmatter(text)
        source_files = _as_list(frontmatter.get("source_files"))
        score, excerpt = _score_excerpt(query, body)
        if score <= 0:
            continue
        items.append(
            EvidenceItem(
                path=rel,
                score=score,
                kind=_kind_from_path(path),
                excerpt=excerpt,
                source_files=source_files,
            )
        )
    items.sort(key=lambda item: (-item.score, item.path))
    return EvidenceBundle(
        query=query,
        items=items[:limit],
        source_paths=[item.path for item in items[:limit]],
        summary=_build_summary(items[:limit]),
    )


def format_evidence_bundle(bundle: EvidenceBundle) -> str:
    lines = ["[Evidence]", f"query: {bundle.query}", ""]
    if not bundle.items:
        lines.append("No evidence found.")
        return "\n".join(lines)
    for index, item in enumerate(bundle.items, start=1):
        lines.append(f"{index}. {item.path}")
        lines.append(f"   - kind: {item.kind}")
        lines.append(f"   - score: {item.score}")
        if item.source_files:
            lines.append(f"   - source_files: {', '.join(item.source_files)}")
        if item.excerpt:
            lines.append(f"   - excerpt: {item.excerpt}")
    return "\n".join(lines)


def _candidate_paths(settings: Settings, query: str, route_result: dict | None, limit: int) -> list[Path]:
    paths: list[Path] = []
    if route_result:
        for anchor in route_result.get("anchors", [])[:limit]:
            rel = str(anchor.get("path") or "")
            if rel:
                paths.append(settings.wiki_root / rel)
        for side in ("local", "global"):
            for candidate in route_result.get(side, {}).get("results", [])[:limit]:
                rel = str(candidate.get("path") or "")
                if rel:
                    paths.append(settings.wiki_root / rel)
    else:
        for folder in ("wiki/topics", "wiki/entities", "wiki/sources", "wiki/analyses"):
            root = settings.wiki_root / folder
            if root.exists():
                paths.extend(sorted(root.rglob("*.md")))
    if not paths:
        paths.extend(_query_paths(settings, query))
    return paths


def _query_paths(settings: Settings, query: str) -> list[Path]:
    tokens = [token for token in re.findall(r"[0-9A-Za-z가-힣_./+-]+", query.lower()) if token]
    candidates: list[Path] = []
    for folder in ("wiki/topics", "wiki/entities", "wiki/sources", "wiki/analyses"):
        root = settings.wiki_root / folder
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            name = path.stem.lower()
            if any(token in name for token in tokens):
                candidates.append(path)
    return candidates


def _read_text(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _to_relative(settings: Settings, path: Path) -> str:
    try:
        return relative_to_root(path, settings.wiki_root)
    except Exception:
        return str(path)


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter = text[4:end]
    body = text[end + 5 :]
    return _parse_frontmatter(frontmatter), body


def _parse_frontmatter(text: str) -> dict[str, object]:
    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_list_key:
            value = line[4:].strip()
            data.setdefault(current_list_key, [])
            if isinstance(data[current_list_key], list):
                data[current_list_key].append(value)
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            data[key] = []
            current_list_key = key
        else:
            data[key] = value
    return data


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _kind_from_path(path: Path) -> str:
    parent = path.parent.name
    return parent if parent else "note"


def _score_excerpt(query: str, body: str) -> tuple[int, str]:
    terms = [term for term in re.findall(r"[0-9A-Za-z가-힣_./+-]+", query.lower()) if term]
    if not terms:
        return 0, ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    score = 0
    matches: list[str] = []
    for line in lines:
        lowered = line.lower()
        hit_count = sum(1 for term in terms if term in lowered)
        if hit_count:
            score += hit_count
            matches.append(line)
        if len(matches) >= 3:
            break
    excerpt = " | ".join(matches[:3])
    return score, excerpt


def _build_summary(items: list[EvidenceItem]) -> str:
    if not items:
        return "No evidence found."
    return ", ".join(item.path for item in items)
