from __future__ import annotations

from pathlib import Path

from agent.jsonl_store import append_jsonl, read_jsonl, update_first
from agent.timeutils import now_iso


def manifest_records(path: Path) -> list[dict]:
    return read_jsonl(path)


def queue_records(path: Path) -> list[dict]:
    return read_jsonl(path)


def has_manifest_hash(manifest_path: Path, sha256: str) -> bool:
    return any(record.get("sha256") == sha256 for record in manifest_records(manifest_path))


def has_queue_hash(queue_path: Path, sha256: str, statuses: set[str] | None = None) -> bool:
    statuses = statuses or {"pending", "processing", "done"}
    return any(
        record.get("sha256") == sha256 and record.get("status") in statuses
        for record in queue_records(queue_path)
    )


def append_manifest_queued(manifest_path: Path, sha256: str, path: str, source: str) -> None:
    append_jsonl(
        manifest_path,
        {
            "sha256": sha256,
            "path": path,
            "status": "queued",
            "source": source,
            "queued_at": now_iso(),
        },
    )


def append_queue_job(queue_path: Path, job_id: str, sha256: str, path: str, source: str) -> None:
    append_jsonl(
        queue_path,
        {
            "job_id": job_id,
            "sha256": sha256,
            "path": path,
            "status": "pending",
            "source": source,
            "queued_at": now_iso(),
        },
    )


def update_queue_job(queue_path: Path, job_id: str, **updates: str) -> dict | None:
    return update_first(queue_path, lambda record: record.get("job_id") == job_id, updates)


def mark_manifest_ingested(
    manifest_path: Path, sha256: str, source_note: str, ingested_at: str | None = None
) -> dict | None:
    return update_first(
        manifest_path,
        lambda record: record.get("sha256") == sha256,
        {
            "status": "ingested",
            "source_note": source_note,
            "ingested_at": ingested_at or now_iso(),
        },
    )


def queue_counts(queue_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in queue_records(queue_path):
        status = str(record.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts
