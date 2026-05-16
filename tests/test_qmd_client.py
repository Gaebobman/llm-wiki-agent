from __future__ import annotations

from agent.config import Settings
from agent.qmd_client import fallback_search, format_route_result, route, search


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
        qmd_mode="disabled",
    )


def test_fallback_search_finds_local_source_notes(tmp_path):
    settings = make_settings(tmp_path)
    source_dir = settings.wiki_root / "wiki" / "sources"
    source_dir.mkdir(parents=True)
    (source_dir / "research-contract.md").write_text(
        "Research contract approval workflow\nNTIS registration",
        encoding="utf-8",
    )

    result = fallback_search(settings, "contract NTIS", mode="local")

    assert result["source"] == "fallback"
    assert result["results"][0]["path"] == "wiki/sources/research-contract.md"
    assert result["results"][0]["matched_terms"] == ["contract", "ntis"]


def test_search_uses_fallback_when_qmd_is_disabled(tmp_path):
    settings = make_settings(tmp_path)
    topic_dir = settings.wiki_root / "wiki" / "topics"
    topic_dir.mkdir(parents=True)
    (topic_dir / "governance.md").write_text("approval governance workflow", encoding="utf-8")

    result = search(settings, "governance", mode="global")

    assert result["source"] == "fallback"
    assert result["results"][0]["path"] == "wiki/topics/governance.md"


def test_route_merges_local_and_global_results(tmp_path):
    settings = make_settings(tmp_path)
    source_dir = settings.wiki_root / "wiki" / "sources"
    topic_dir = settings.wiki_root / "wiki" / "topics"
    source_dir.mkdir(parents=True)
    topic_dir.mkdir(parents=True)
    (source_dir / "contract.md").write_text("contract approval", encoding="utf-8")
    (topic_dir / "approval.md").write_text("approval workflow", encoding="utf-8")

    routed = route(settings, "approval")
    text = format_route_result(routed)

    assert [anchor["path"] for anchor in routed["anchors"]] == [
        "wiki/sources/contract.md",
        "wiki/topics/approval.md",
    ]
    assert "Local 후보" in text
    assert "Global 후보" in text
