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
