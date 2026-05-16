from __future__ import annotations

import argparse
import sys
import time

from agent.config import ensure_runtime_dirs, load_settings
from agent.ingest_worker import process_pending
from agent.manifest import queue_counts
from agent.raw_scanner import scan_raw_sources
from agent.status import status_text
from agent.telegram_bot import TelegramBot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM-Wiki Agent")
    parser.add_argument("--once", choices=["status", "scan", "queue", "ingest"], help="run one action")
    args = parser.parse_args(argv)

    settings = load_settings()
    ensure_runtime_dirs(settings)

    if args.once == "status":
        print(status_text(settings))
        return 0
    if args.once == "scan":
        result = scan_raw_sources(settings)
        print(
            f"scan complete: scanned={result.scanned} queued={result.queued} skipped={result.skipped}"
        )
        return 0
    if args.once == "queue":
        counts = queue_counts(settings.queue_path)
        print("queue: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "empty"))
        return 0
    if args.once == "ingest":
        result = process_pending(settings, limit=None)
        print(
            f"ingest complete: processed={result.processed} "
            f"failed={result.failed} remaining={result.remaining}"
        )
        return 0

    if settings.telegram_bot_token:
        TelegramBot(settings).run_polling()
        return 0

    print("TELEGRAM_BOT_TOKEN is not configured; running scanner/ingest loop only.")
    while True:
        scan_raw_sources(settings)
        process_pending(settings, limit=None)
        time.sleep(min(settings.scan_interval_seconds, settings.ingest_interval_seconds))


if __name__ == "__main__":
    sys.exit(main())
