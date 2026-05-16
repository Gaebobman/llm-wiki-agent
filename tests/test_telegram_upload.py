from __future__ import annotations

from agent.config import Settings
from agent.jsonl_store import read_jsonl
from agent.telegram_bot import TelegramBot, safe_upload_name, unique_raw_upload_path


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token="token",
        telegram_allowed_user_ids=set(),
    )


class FakeTelegramBot(TelegramBot):
    def _request(self, method, params):
        assert method == "getFile"
        return {"result": {"file_path": "documents/sample.md"}}

    def download_file(self, telegram_file_path, target_path):
        assert telegram_file_path == "documents/sample.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("uploaded contract", encoding="utf-8")


def test_safe_upload_name_removes_path_parts():
    assert safe_upload_name("../bad/name.md") == "name.md"


def test_unique_raw_upload_path_does_not_overwrite_existing_file(tmp_path):
    settings = make_settings(tmp_path)
    settings.raw_sources_dir.mkdir(parents=True)
    (settings.raw_sources_dir / "sample.md").write_text("old", encoding="utf-8")

    assert unique_raw_upload_path(settings, "sample.md").name == "sample-2.md"


def test_document_upload_saves_raw_file_and_queues_ingest(tmp_path):
    settings = make_settings(tmp_path)
    bot = FakeTelegramBot(settings)

    response = bot.handle_document_upload({"file_id": "file-1", "file_name": "sample.md"})

    assert "Telegram upload queued" in response
    assert (settings.raw_sources_dir / "sample.md").read_text(encoding="utf-8") == "uploaded contract"
    queue = read_jsonl(settings.queue_path)
    assert queue[0]["source"] == "telegram_upload"
    assert queue[0]["path"] == "raw/sources/sample.md"
