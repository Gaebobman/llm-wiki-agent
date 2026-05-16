from __future__ import annotations

from agent.config import Settings
from agent.jsonl_store import read_jsonl
from agent.raw_scanner import scan_raw_sources


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
    )


def test_scan_queues_new_raw_file_once(tmp_path):
    settings = make_settings(tmp_path)
    raw_dir = settings.raw_sources_dir
    raw_dir.mkdir(parents=True)
    (raw_dir / "sample.md").write_text("# Sample\n", encoding="utf-8")

    first = scan_raw_sources(settings)
    second = scan_raw_sources(settings)

    assert first.scanned == 1
    assert first.queued == 1
    assert second.scanned == 1
    assert second.queued == 0
    assert len(read_jsonl(settings.queue_path)) == 1
    assert len(read_jsonl(settings.manifest_path)) == 1


def test_scan_ignores_temp_files(tmp_path):
    settings = make_settings(tmp_path)
    raw_dir = settings.raw_sources_dir
    raw_dir.mkdir(parents=True)
    (raw_dir / ".hidden.md").write_text("hidden", encoding="utf-8")
    (raw_dir / "upload.tmp").write_text("tmp", encoding="utf-8")
    (raw_dir / "~$office.docx").write_text("lock", encoding="utf-8")

    result = scan_raw_sources(settings)

    assert result.scanned == 0
    assert result.queued == 0
    assert result.skipped == 3
