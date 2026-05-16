from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from agent.config import Settings, ensure_runtime_dirs, load_settings
from agent.file_utils import relative_to_root, sha256_file
from agent.manifest import (
    append_manifest_queued,
    append_queue_job,
    has_manifest_hash,
    has_queue_hash,
)
from agent.timeutils import now_iso


IGNORE_PATTERNS = (
    ".*",
    "*.tmp",
    "*.part",
    "*.crdownload",
    "~$*",
    ".DS_Store",
    "Thumbs.db",
    "Desktop.ini",
)


@dataclass(frozen=True)
class ScanResult:
    scanned: int
    queued: int
    skipped: int
    missing_raw_dir: bool = False


@dataclass(frozen=True)
class QueueFileResult:
    queued: bool
    skipped: bool
    job_id: str | None
    sha256: str
    path: str


def should_ignore(path: Path) -> bool:
    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in IGNORE_PATTERNS)


def queue_raw_file(settings: Settings, path: Path, source: str) -> QueueFileResult:
    sha256 = sha256_file(path)
    rel_path = relative_to_root(path, settings.wiki_root)
    if has_manifest_hash(settings.manifest_path, sha256) or has_queue_hash(settings.queue_path, sha256):
        return QueueFileResult(
            queued=False,
            skipped=True,
            job_id=None,
            sha256=sha256,
            path=rel_path,
        )

    job_id = f"ingest_{now_iso().replace('-', '').replace(':', '').replace('+', '_')}_{sha256[:8]}"
    append_manifest_queued(settings.manifest_path, sha256, rel_path, source)
    append_queue_job(settings.queue_path, job_id, sha256, rel_path, source)
    return QueueFileResult(
        queued=True,
        skipped=False,
        job_id=job_id,
        sha256=sha256,
        path=rel_path,
    )


def scan_raw_sources(settings: Settings, source: str = "drive_raw_scan") -> ScanResult:
    ensure_runtime_dirs(settings)
    raw_dir = settings.raw_sources_dir
    if not raw_dir.exists():
        return ScanResult(scanned=0, queued=0, skipped=0, missing_raw_dir=True)

    scanned = 0
    queued = 0
    skipped = 0
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        if should_ignore(path.relative_to(raw_dir)):
            skipped += 1
            continue

        scanned += 1
        result = queue_raw_file(settings, path, source)
        if result.skipped:
            skipped += 1
            continue
        if result.queued:
            queued += 1

    return ScanResult(scanned=scanned, queued=queued, skipped=skipped)


def main() -> None:
    result = scan_raw_sources(load_settings())
    print(
        f"raw scan: scanned={result.scanned} queued={result.queued} "
        f"skipped={result.skipped} missing_raw_dir={result.missing_raw_dir}"
    )


if __name__ == "__main__":
    main()
