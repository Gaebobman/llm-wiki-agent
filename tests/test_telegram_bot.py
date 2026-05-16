from __future__ import annotations

from agent.config import Settings
from agent.telegram_bot import dispatch_command


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


def test_route_command_returns_search_routing_result(tmp_path):
    settings = make_settings(tmp_path)
    source_dir = settings.wiki_root / "wiki" / "sources"
    source_dir.mkdir(parents=True)
    (source_dir / "contract.md").write_text("contract approval", encoding="utf-8")

    response = dispatch_command(settings, "/route contract")

    assert "[Search Routing 결과]" in response
    assert "wiki/sources/contract.md" in response


def test_local_command_requires_query(tmp_path):
    settings = make_settings(tmp_path)

    assert dispatch_command(settings, "/local") == "/local requires a query"


def test_bases_command_creates_search_routing_base(tmp_path):
    settings = make_settings(tmp_path)

    response = dispatch_command(settings, "/bases")

    assert "search routing base ready" in response
    assert (settings.wiki_root / "wiki" / "bases" / "search-routing.base").exists()
