from __future__ import annotations

from agent.config import Settings
from agent.evidence_retriever import format_evidence_bundle, retrieve_evidence


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
    )


def test_retrieve_evidence_reads_source_note_and_source_files(tmp_path):
    settings = make_settings(tmp_path)
    note_dir = settings.wiki_root / "wiki" / "sources"
    raw_dir = settings.wiki_root / "raw" / "sources"
    note_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (note_dir / "research-contract.md").write_text(
        "---\nsource_files:\n  - raw/sources/research-contract.pdf\n---\n# Research Contract\n\napproval workflow and contract review\n",
        encoding="utf-8",
    )
    (raw_dir / "research-contract.pdf").write_text(
        "approval workflow\ncontract review\n",
        encoding="utf-8",
    )

    bundle = retrieve_evidence(settings, "contract review")

    assert bundle.items
    assert bundle.items[0].path == "wiki/sources/research-contract.md"
    assert "contract review" in bundle.items[0].excerpt
    assert "wiki/sources/research-contract.md" in format_evidence_bundle(bundle)
