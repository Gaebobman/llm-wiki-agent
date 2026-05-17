from __future__ import annotations

from agent.config import Settings
from agent.patch_manager import create_patch_for_update
from agent.policies import ensure_wiki_markdown_target


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
    )


def test_policy_blocks_patch_target_outside_wiki_root(tmp_path):
    settings = make_settings(tmp_path)
    outside = tmp_path / "outside.md"

    try:
        ensure_wiki_markdown_target(settings, outside)
    except ValueError as exc:
        assert "outside wiki root" in str(exc)
    else:
        raise AssertionError("expected policy block")


def test_policy_blocks_route_anchor_path_traversal(tmp_path):
    settings = make_settings(tmp_path)
    target = settings.wiki_root / "wiki" / "topics" / "safe.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Safe\n", encoding="utf-8")

    try:
        create_patch_for_update(
            settings,
            "라우팅 설명을 보강해줘",
            route_result={"anchors": [{"path": "../../outside.md"}]},
        )
    except ValueError as exc:
        assert "outside wiki root" in str(exc)
    else:
        raise AssertionError("expected policy block")
