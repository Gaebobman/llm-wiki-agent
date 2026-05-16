from __future__ import annotations

from agent.config import Settings
from agent.patch_manager import apply_patch, create_patch_for_update, reject_patch


def make_settings(tmp_path):
    return Settings(
        wiki_root=tmp_path / "vault",
        agent_state_dir=tmp_path / "agent-state",
        config_dir=tmp_path / "config",
        qmd_config=tmp_path / "config" / "qmd.yaml",
        telegram_bot_token=None,
        telegram_allowed_user_ids=set(),
    )


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
