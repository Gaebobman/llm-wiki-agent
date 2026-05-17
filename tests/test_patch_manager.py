from __future__ import annotations

import sys
from dataclasses import replace

from agent.config import Settings
from agent.patch_manager import approve_patch, apply_patch, create_patch_for_update, reject_patch


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
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


def test_create_apply_and_reject_patch(tmp_path):
    settings = make_settings(tmp_path)
    target = settings.wiki_root / "wiki" / "topics" / "routing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Routing\n\nExisting body\n", encoding="utf-8")

    result = create_patch_for_update(
        settings,
        "라우팅 설명을 보강해줘",
        route_result={"anchors": [{"path": "wiki/topics/routing.md"}]},
    )
    assert result.record.status == "pending"
    assert result.record.target_file == "wiki/topics/routing.md"
    assert (settings.patches_dir / result.record.patch_id / "metadata.json").exists()

    applied = apply_patch(settings, result.record.patch_id)
    assert applied.status == "applied"
    assert "Update Proposal" in target.read_text(encoding="utf-8")

    rejected = reject_patch(settings, result.record.patch_id)
    assert rejected.status == "rejected"


def test_high_risk_patch_requires_second_approval(tmp_path):
    settings = make_settings(tmp_path)
    settings = replace(
        settings,
        llm_planner_command=make_planner(tmp_path, destructive=True, risk_level="high"),
    )
    target = settings.wiki_root / "wiki" / "topics" / "routing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Routing\n\nExisting body\n", encoding="utf-8")

    result = create_patch_for_update(
        settings,
        "라우팅 설명을 삭제해줘",
        route_result={"anchors": [{"path": "wiki/topics/routing.md"}]},
    )
    assert result.record.risk_level == "high"

    try:
        apply_patch(settings, result.record.patch_id)
    except ValueError as exc:
        assert "requires /approve" in str(exc)
    else:
        raise AssertionError("expected second approval block")

    approved = approve_patch(settings, result.record.patch_id)
    assert approved.status == "approved"
    applied = apply_patch(settings, result.record.patch_id)
    assert applied.status == "applied"


def test_patch_schema_validation_blocks_tampered_after_file(tmp_path):
    settings = make_settings(tmp_path)
    target = settings.wiki_root / "wiki" / "topics" / "routing.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Routing\n\nExisting body\n", encoding="utf-8")

    result = create_patch_for_update(
        settings,
        "라우팅 설명을 보강해줘",
        route_result={"anchors": [{"path": "wiki/topics/routing.md"}]},
    )
    after_path = settings.patches_dir / result.record.patch_id / "after.md"
    after_path.write_text("# Tampered\n", encoding="utf-8")

    try:
        apply_patch(settings, result.record.patch_id)
    except ValueError as exc:
        assert "after hash mismatch" in str(exc)
    else:
        raise AssertionError("expected patch hash validation block")
