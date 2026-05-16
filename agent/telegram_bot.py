from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from agent.config import Settings
from agent.ingest_worker import process_pending
from agent.manifest import queue_counts
from agent.raw_scanner import scan_raw_sources
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
        if chat_id is None or not text:
            return
        if self.settings.telegram_allowed_user_ids and user_id not in self.settings.telegram_allowed_user_ids:
            self.send_message(chat_id, "Unauthorized user.")
            return
        self.send_message(chat_id, dispatch_command(self.settings, text))

    def send_message(self, chat_id: int, text: str) -> None:
        self._request("sendMessage", {"chat_id": chat_id, "text": text})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(f"{self.api_base}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


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
    return "Supported commands: /status, /scan, /queue, /ingest"
