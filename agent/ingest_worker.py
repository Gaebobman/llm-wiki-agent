from __future__ import annotations

from dataclasses import dataclass

from agent.config import Settings, ensure_runtime_dirs, load_settings
from agent.file_utils import relative_to_root
from agent.manifest import mark_manifest_ingested, queue_records, update_queue_job
from agent.qmd_client import refresh_changed
from agent.timeutils import now_iso
from agent.wiki_writer import append_index_entry, append_log_entry, write_source_note


@dataclass(frozen=True)
class IngestResult:
    processed: int
    failed: int
    remaining: int


def process_pending(settings: Settings, limit: int | None = 1) -> IngestResult:
    ensure_runtime_dirs(settings)
    processed = 0
    failed = 0

    for job in queue_records(settings.queue_path):
        if job.get("status") != "pending":
            continue
        if limit is not None and processed + failed >= limit:
            break
        job_id = str(job["job_id"])
        update_queue_job(settings.queue_path, job_id, status="processing", started_at=now_iso())
        try:
            raw_rel_path = str(job["path"])
            sha256 = str(job["sha256"])
            source = str(job.get("source", "drive_raw_scan"))
            note_path = write_source_note(settings, raw_rel_path, sha256, source)
            rel_note = relative_to_root(note_path, settings.wiki_root)
            append_index_entry(settings, note_path, raw_rel_path)
            append_log_entry(settings, raw_rel_path, note_path, sha256, source)
            mark_manifest_ingested(settings.manifest_path, sha256, rel_note)
            refresh_changed(settings)
            update_queue_job(
                settings.queue_path,
                job_id,
                status="done",
                source_note=rel_note,
                finished_at=now_iso(),
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001 - job failure must be persisted.
            update_queue_job(
                settings.queue_path,
                job_id,
                status="failed",
                error=str(exc),
                finished_at=now_iso(),
            )
            failed += 1

    remaining = sum(1 for job in queue_records(settings.queue_path) if job.get("status") == "pending")
    return IngestResult(processed=processed, failed=failed, remaining=remaining)


def main() -> None:
    result = process_pending(load_settings(), limit=None)
    print(
        f"ingest: processed={result.processed} failed={result.failed} "
        f"remaining={result.remaining}"
    )


if __name__ == "__main__":
    main()
