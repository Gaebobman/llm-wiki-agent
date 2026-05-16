from __future__ import annotations

from agent.bases_writer import ensure_search_routing_base
from agent.config import Settings


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
    )


def test_ensure_search_routing_base_creates_expected_views(tmp_path):
    settings = make_settings(tmp_path)

    path = ensure_search_routing_base(settings)

    assert path == settings.wiki_root / "wiki" / "bases" / "search-routing.base"
    text = path.read_text(encoding="utf-8")
    assert "name: Local Candidates" in text
    assert "name: Global Candidates" in text
    assert "name: Hybrid Review" in text
    assert "file.inFolder(\"wiki/sources\")" in text
    assert "source_files:" in text
