from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from agent.bases_writer import ensure_search_routing_base
from agent.config import Settings
from agent.ingest_worker import process_pending
from agent.manifest import queue_counts
from agent.qmd_client import format_route_result, format_search_result, route, search
from agent.raw_scanner import queue_raw_file, scan_raw_sources
from agent.status import status_text


@dataclass
class TelegramBot:
    settings: Settings
    offset: int | None = None

    @property
    def api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    def run_polling(self) -> None:
        if not self.settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        while True:
            for update in self.get_updates():
                self.handle_update(update)
            time.sleep(1)

    def get_updates(self) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": 20}
        if self.offset is not None:
            params["offset"] = self.offset
        payload = self._request("getUpdates", params)
        updates = payload.get("result", [])
        for update in updates:
            self.offset = int(update["update_id"]) + 1
        return updates

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = chat.get("id")
        user_id = user.get("id")
        text = str(message.get("text") or "").strip()
        document = message.get("document")
        if chat_id is None or (not text and not document):
            return
        if self.settings.telegram_allowed_user_ids and user_id not in self.settings.telegram_allowed_user_ids:
            self.send_message(chat_id, "Unauthorized user.")
            return
        if document:
            self.send_message(chat_id, self.handle_document_upload(document))
            return
        self.send_message(chat_id, dispatch_command(self.settings, text))

    def send_message(self, chat_id: int, text: str) -> None:
        self._request("sendMessage", {"chat_id": chat_id, "text": text})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(f"{self.api_base}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def handle_document_upload(self, document: dict[str, Any]) -> str:
        file_id = str(document.get("file_id") or "")
        if not file_id:
            return "upload failed: missing Telegram file_id"
        file_name = safe_upload_name(str(document.get("file_name") or file_id))
        target_path = unique_raw_upload_path(self.settings, file_name)
        payload = self._request("getFile", {"file_id": file_id})
        file_path = payload.get("result", {}).get("file_path")
        if not file_path:
            return "upload failed: Telegram did not return file_path"
        self.download_file(str(file_path), target_path)
        result = queue_raw_file(self.settings, target_path, "telegram_upload")
        if result.queued:
            return (
                "[Telegram upload queued]\n"
                f"file: {result.path}\n"
                f"job_id: {result.job_id}\n"
                f"sha256: {result.sha256}"
            )
        return f"[Telegram upload skipped]\nfile: {result.path}\nreason: duplicate hash"

    def download_file(self, telegram_file_path: str, target_path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{self.api_base.replace('/bot', '/file/bot')}/{telegram_file_path}"
        with urllib.request.urlopen(url, timeout=120) as response:
            target_path.write_bytes(response.read())


def safe_upload_name(file_name: str) -> str:
    cleaned = file_name.strip().replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9가-힣._ -]+", "-", cleaned).strip(" .-")
    return cleaned or "telegram-upload"


def unique_raw_upload_path(settings: Settings, file_name: str):
    path = settings.raw_sources_dir / file_name
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = settings.raw_sources_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def dispatch_command(settings: Settings, text: str) -> str:
    command = text.split(maxsplit=1)[0].lower()
    if command == "/status":
        return status_text(settings)
    if command == "/scan":
        result = scan_raw_sources(settings)
        return f"scan complete: scanned={result.scanned} queued={result.queued} skipped={result.skipped}"
    if command == "/queue":
        counts = queue_counts(settings.queue_path)
        return "queue: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "empty")
    if command == "/ingest":
        result = process_pending(settings, limit=None)
        return (
            f"ingest complete: processed={result.processed} "
            f"failed={result.failed} remaining={result.remaining}"
        )
    if command == "/bases":
        path = ensure_search_routing_base(settings)
        return f"search routing base ready: {path}"
    if command in {"/local", "/global", "/search", "/route"}:
        query = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        if not query:
            return f"{command} requires a query"
        if command == "/route":
            return format_route_result(route(settings, query=query))
        mode = "global" if command == "/global" else "local"
        if command == "/search":
            return format_route_result(route(settings, query=query))
        return format_search_result(search(settings, query=query, mode=mode))
    return "Supported commands: /status, /scan, /queue, /ingest, /bases, /local, /global, /search, /route"
