from __future__ import annotations

import zipfile

from agent.config import Settings
from agent.ingest_worker import process_pending
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


def test_ingest_creates_source_note_index_and_log(tmp_path):
    settings = make_settings(tmp_path)
    settings.raw_sources_dir.mkdir(parents=True)
    (settings.raw_sources_dir / "Research Contract.md").write_text("contract steps", encoding="utf-8")
    scan_raw_sources(settings)

    result = process_pending(settings, limit=None)

    assert result.processed == 1
    assert result.failed == 0
    source_note = settings.wiki_sources_dir / "research-contract.md"
    assert source_note.exists()
    note_text = source_note.read_text(encoding="utf-8")
    assert "source_files:" in note_text
    assert "raw/sources/Research Contract.md" in note_text
    assert "contract steps" in note_text
    assert "research-contract" in settings.wiki_index_path.read_text(encoding="utf-8")
    assert "Ingested `raw/sources/Research Contract.md`" in settings.wiki_log_path.read_text(
        encoding="utf-8"
    )
    assert read_jsonl(settings.queue_path)[0]["status"] == "done"
    assert read_jsonl(settings.manifest_path)[0]["status"] == "ingested"


def test_ingest_extracts_docx_text(tmp_path):
    settings = make_settings(tmp_path)
    settings.raw_sources_dir.mkdir(parents=True)
    docx_path = settings.raw_sources_dir / "Policy.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Approval policy</w:t></w:r></w:p>
                <w:p><w:r><w:t>Contract review</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """,
        )
    scan_raw_sources(settings)

    result = process_pending(settings, limit=None)

    assert result.processed == 1
    source_note = settings.wiki_sources_dir / "policy.md"
    note_text = source_note.read_text(encoding="utf-8")
    assert "Approval policy" in note_text
    assert "Contract review" in note_text
