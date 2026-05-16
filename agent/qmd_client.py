from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent.config import Settings, load_settings


@dataclass(frozen=True)
class QmdResult:
    ok: bool
    message: str
    source: str = "fallback"
    data: dict | None = None


def refresh_changed(settings: Settings) -> QmdResult:
    command = _refresh_command(settings)
    if command is None:
        return QmdResult(
            ok=True,
            message="qmd refresh skipped: no qmd command available",
            source="fallback",
        )
    result = _run_command(command, settings)
    return QmdResult(
        ok=result.returncode == 0,
        message=(result.stdout or result.stderr or "qmd refresh completed").strip(),
        source="cli",
    )


def search(settings: Settings, query: str, mode: str = "local", top_k: int = 10) -> dict:
    command = _search_command(settings, query=query, mode=mode, top_k=top_k)
    if command is not None:
        result = _run_command(command, settings)
        if result.returncode == 0:
            return _parse_cli_search_result(settings, query, mode, result.stdout)
        fallback = fallback_search(settings, query=query, mode=mode, top_k=top_k)
        fallback["message"] = f"qmd cli failed; fallback search used: {result.stderr.strip()}"
        return fallback
    return fallback_search(settings, query=query, mode=mode, top_k=top_k)


def fallback_search(settings: Settings, query: str, mode: str = "local", top_k: int = 10) -> dict:
    terms = _query_terms(query)
    folders = _mode_folders(mode)
    candidates: list[dict] = []
    for path in _wiki_markdown_files(settings, folders):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        matched_terms = [term for term in terms if term in lowered]
        if not matched_terms:
            continue
        rel_path = path.relative_to(settings.wiki_root).as_posix()
        score = len(matched_terms) * 10 + sum(lowered.count(term) for term in matched_terms)
        candidates.append(
            {
                "path": rel_path,
                "score": score,
                "matched_terms": matched_terms,
                "matched_lines": _matched_lines(text, matched_terms),
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["path"]))
    return {
        "query": query,
        "mode": mode,
        "source": "fallback",
        "results": candidates[:top_k],
        "message": "fallback wiki markdown search used; configure qmd for BM25/vector/rerank",
        "config": str(settings.qmd_config),
    }


def route(settings: Settings, query: str, top_k: int = 5) -> dict:
    local = search(settings, query=query, mode="local", top_k=top_k)
    global_ = search(settings, query=query, mode="global", top_k=top_k)
    anchors = _merge_anchors(local.get("results", []), global_.get("results", []), top_k=top_k)
    return {
        "query": query,
        "local": local,
        "global": global_,
        "anchors": anchors,
    }


def format_search_result(result: dict) -> str:
    lines = [
        "[Search 결과]",
        f"mode: {result.get('mode')}",
        f"source: {result.get('source')}",
        f"query: {result.get('query')}",
        "",
    ]
    results = result.get("results") or []
    if not results:
        lines.append("검색 결과가 없습니다.")
        lines.append(str(result.get("message", "")))
        return "\n".join(lines).strip()
    for index, item in enumerate(results, start=1):
        terms = ", ".join(item.get("matched_terms", []))
        lines.append(f"{index}. {item.get('path')}")
        lines.append(f"   - score: {item.get('score')}")
        if terms:
            lines.append(f"   - matched_terms: {terms}")
    return "\n".join(lines)


def format_route_result(result: dict) -> str:
    lines = ["[Search Routing 결과]", "", f"질문: {result.get('query')}", "", "Local 후보:"]
    _append_numbered(lines, result.get("local", {}).get("results", []))
    lines.extend(["", "Global 후보:"])
    _append_numbered(lines, result.get("global", {}).get("results", []))
    lines.extend(["", "추천 Anchor:"])
    anchors = result.get("anchors") or []
    if anchors:
        for anchor in anchors:
            lines.append(f"- {anchor.get('path')} (score: {anchor.get('score')})")
    else:
        lines.append("- 없음")
    return "\n".join(lines)


def _refresh_command(settings: Settings) -> list[str] | None:
    if settings.qmd_refresh_command:
        return _template_command(settings.qmd_refresh_command, settings, query="", mode="", top_k=0)
    if settings.qmd_mode == "disabled":
        return None
    if shutil.which(settings.qmd_binary) is None:
        return None
    return [settings.qmd_binary, "refresh", "--config", str(settings.qmd_config)]


def _search_command(settings: Settings, query: str, mode: str, top_k: int) -> list[str] | None:
    if settings.qmd_search_command:
        return _template_command(settings.qmd_search_command, settings, query=query, mode=mode, top_k=top_k)
    if settings.qmd_mode == "disabled":
        return None
    if shutil.which(settings.qmd_binary) is None:
        return None
    return [
        settings.qmd_binary,
        "search",
        "--config",
        str(settings.qmd_config),
        "--profile",
        mode,
        "--json",
        "--top-k",
        str(top_k),
        query,
    ]


def _template_command(template: str, settings: Settings, query: str, mode: str, top_k: int) -> list[str]:
    rendered = template.format(
        config=str(settings.qmd_config),
        query=query,
        mode=mode,
        top_k=top_k,
        vault=str(settings.wiki_root),
    )
    return shlex.split(rendered)


def _run_command(command: list[str], settings: Settings) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=settings.wiki_root,
        text=True,
        capture_output=True,
        timeout=settings.qmd_timeout_seconds,
        check=False,
    )


def _parse_cli_search_result(settings: Settings, query: str, mode: str, stdout: str) -> dict:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "query": query,
            "mode": mode,
            "source": "cli",
            "results": [],
            "message": stdout.strip(),
            "config": str(settings.qmd_config),
        }
    if isinstance(payload, dict):
        payload.setdefault("query", query)
        payload.setdefault("mode", mode)
        payload.setdefault("source", "cli")
        payload.setdefault("config", str(settings.qmd_config))
        payload.setdefault("results", [])
        return payload
    return {
        "query": query,
        "mode": mode,
        "source": "cli",
        "results": payload if isinstance(payload, list) else [],
        "config": str(settings.qmd_config),
    }


def _query_terms(query: str) -> list[str]:
    try:
        terms = shlex.split(query)
    except ValueError:
        terms = query.split()
    return [term.lower() for term in terms if term.strip()]


def _mode_folders(mode: str) -> tuple[str, ...]:
    if mode == "local":
        return ("wiki/entities", "wiki/sources", "wiki/analyses")
    if mode == "global":
        return ("wiki/topics", "wiki/analyses")
    return ("wiki",)


def _wiki_markdown_files(settings: Settings, folders: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for folder in folders:
        root = settings.wiki_root / folder
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.md") if path.name != "log.md")
    return sorted(set(files))


def _matched_lines(text: str, matched_terms: list[str], limit: int = 3) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(term in lowered for term in matched_terms):
            lines.append(line.strip())
        if len(lines) >= limit:
            break
    return lines


def _merge_anchors(local_results: list[dict], global_results: list[dict], top_k: int) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in local_results + global_results:
        path = str(item.get("path", ""))
        if not path:
            continue
        current = merged.setdefault(path, {"path": path, "score": 0, "sources": []})
        current["score"] += int(item.get("score") or 0)
        current["sources"].append(item)
    return sorted(merged.values(), key=lambda item: (-item["score"], item["path"]))[:top_k]


def _append_numbered(lines: list[str], results: list[dict]) -> None:
    if not results:
        lines.append("없음")
        return
    for index, item in enumerate(results, start=1):
        lines.append(f"{index}. {item.get('path')}")
        lines.append(f"   - score: {item.get('score')}")
        terms = ", ".join(item.get("matched_terms", []))
        if terms:
            lines.append(f"   - matched_terms: {terms}")


def main() -> None:
    settings = load_settings()
    print(refresh_changed(settings).message)


if __name__ == "__main__":
    main()
