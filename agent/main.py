from __future__ import annotations

import argparse
import sys
import time

from agent.bases_writer import ensure_search_routing_base
from agent.config import ensure_runtime_dirs, load_settings
from agent.ingest_worker import process_pending
from agent.manifest import queue_counts
from agent.qmd_client import format_route_result, format_search_result, route, search
from agent.raw_scanner import scan_raw_sources
from agent.status import status_text
from agent.telegram_bot import TelegramBot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM-Wiki Agent")
    parser.add_argument(
        "--once",
        choices=["status", "scan", "queue", "ingest", "bases", "local", "global", "route"],
        help="run one action",
    )
    parser.add_argument("query", nargs="*", help="query for local/global/route actions")
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
    if args.once == "bases":
        path = ensure_search_routing_base(settings)
        print(f"search routing base ready: {path}")
        return 0
    if args.once in {"local", "global"}:
        query = " ".join(args.query).strip()
        if not query:
            print(f"--once {args.once} requires a query", file=sys.stderr)
            return 2
        print(format_search_result(search(settings, query=query, mode=args.once)))
        return 0
    if args.once == "route":
        query = " ".join(args.query).strip()
        if not query:
            print("--once route requires a query", file=sys.stderr)
            return 2
        print(format_route_result(route(settings, query=query)))
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
