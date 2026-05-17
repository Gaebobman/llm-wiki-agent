from __future__ import annotations

import sys
from dataclasses import replace

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


def make_planner(tmp_path, *, destructive: bool, risk_level: str):
    planner = tmp_path / f"planner_{risk_level}.py"
    planner.write_text(
        "\n".join(
            [
                "import json, sys",
                "json.loads(sys.stdin.read())",
                "print(json.dumps({",
                "  'crud_action': 'update',",
                "  'intent': 'update_existing_page',",
                f"  'destructive_action': {str(destructive)},",
                f"  'risk_level': '{risk_level}',",
                "  'requires_approval': True,",
                "  'local_query': {'terms': ['routing'], 'entities': ['routing']},",
                "  'global_query': {'themes': ['routing'], 'relations': []},",
                "  'update_summary': 'planner supplied update',",
                "  'confidence': 0.9,",
                "  'rationale': 'test planner'",
                "}))",
            ]
        ),
        encoding="utf-8",
    )
    return f"{sys.executable} {planner}"


def test_update_command_creates_patch_and_apply_reject_flow(tmp_path):
    settings = make_settings(tmp_path)
    target = settings.wiki_root / "wiki" / "topics" / "routing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Routing\n", encoding="utf-8")

    response = dispatch_command(settings, "/update 라우팅 설명을 보강해줘")
    assert "[승인 필요]" in response

    patch_id = next(settings.patches_dir.glob("*/metadata.json")).parent.name
    assert dispatch_command(settings, f"/apply {patch_id}").startswith("[Applied]")
    assert dispatch_command(settings, f"/reject {patch_id}").startswith("[Rejected]")
    assert patch_id in dispatch_command(settings, "/patches")
    assert patch_id in dispatch_command(settings, "/logs")


def test_command_policy_blocks_unauthorized_write_command(tmp_path):
    settings = Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids={123},
        qmd_mode="disabled",
    )

    assert dispatch_command(settings, "/update 라우팅 설명을 보강해줘", user_id=999) == "Unauthorized command."


def test_high_risk_update_command_requires_approve_before_apply(tmp_path):
    settings = make_settings(tmp_path)
    settings = replace(
        settings,
        llm_planner_command=make_planner(tmp_path, destructive=True, risk_level="high"),
    )
    target = settings.wiki_root / "wiki" / "topics" / "routing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Routing\n", encoding="utf-8")

    response = dispatch_command(settings, "/update 라우팅 설명을 삭제해줘")
    assert "/approve" in response
    patch_id = next(settings.patches_dir.glob("*/metadata.json")).parent.name
    assert "requires /approve" in dispatch_command(settings, f"/apply {patch_id}")
    assert dispatch_command(settings, f"/approve {patch_id}").startswith("[Approved]")
    assert dispatch_command(settings, f"/apply {patch_id}").startswith("[Applied]")
