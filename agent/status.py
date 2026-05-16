from __future__ import annotations

from agent.config import Settings
from agent.manifest import manifest_records, queue_counts


def status_text(settings: Settings) -> str:
    counts = queue_counts(settings.queue_path)
    manifest_count = len(manifest_records(settings.manifest_path))
    queue_summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "empty"
    return "\n".join(
        [
            "[LLM-Wiki Agent Status]",
            f"WIKI_ROOT: {settings.wiki_root}",
            f"AGENT_STATE_DIR: {settings.agent_state_dir}",
            f"raw/sources exists: {settings.raw_sources_dir.exists()}",
            f"manifest records: {manifest_count}",
            f"queue: {queue_summary}",
        ]
    )
