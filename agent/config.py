from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENXML_PARSER_SRC = PROJECT_ROOT / "vendor" / "openxml-parser" / "src"


@dataclass(frozen=True)
class Settings:
    wiki_root: Path
    agent_state_dir: Path
    config_dir: Path
    qmd_config: Path
    telegram_bot_token: str | None
    telegram_allowed_user_ids: set[int]
    qmd_mode: str = "auto"
    qmd_binary: str = "qmd"
    qmd_timeout_seconds: int = 30
    qmd_refresh_command: str | None = None
    qmd_search_command: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_planner_command: str | None = None
    llm_planner_timeout_seconds: int = 30
    openxml_parser_src: Path | None = DEFAULT_OPENXML_PARSER_SRC
    extract_openxml_assets: bool = True
    scan_interval_seconds: int = 300
    ingest_interval_seconds: int = 60

    @property
    def raw_sources_dir(self) -> Path:
        return self.wiki_root / "raw" / "sources"

    @property
    def wiki_sources_dir(self) -> Path:
        return self.wiki_root / "wiki" / "sources"

    @property
    def wiki_index_path(self) -> Path:
        return self.wiki_root / "wiki" / "index.md"

    @property
    def wiki_log_path(self) -> Path:
        return self.wiki_root / "wiki" / "log.md"

    @property
    def manifest_path(self) -> Path:
        return self.agent_state_dir / "file_manifest.jsonl"

    @property
    def queue_path(self) -> Path:
        return self.agent_state_dir / "ingest_queue.jsonl"

    @property
    def logs_dir(self) -> Path:
        return self.agent_state_dir / "logs"

    @property
    def locks_dir(self) -> Path:
        return self.agent_state_dir / "locks"

    @property
    def patches_dir(self) -> Path:
        return self.agent_state_dir / "patches"


def load_settings() -> Settings:
    wiki_root = Path(os.getenv("WIKI_ROOT", "/data/vault"))
    agent_state_dir = Path(os.getenv("AGENT_STATE_DIR", "/data/agent-state"))
    config_dir = Path(os.getenv("CONFIG_DIR", "/data/config"))
    qmd_config = Path(os.getenv("QMD_CONFIG", str(config_dir / "qmd.yaml")))
    allowed = _parse_allowed_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    return Settings(
        wiki_root=wiki_root,
        agent_state_dir=agent_state_dir,
        config_dir=config_dir,
        qmd_config=qmd_config,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
        telegram_allowed_user_ids=allowed,
        qmd_mode=os.getenv("QMD_MODE", "auto"),
        qmd_binary=os.getenv("QMD_BINARY", "qmd"),
        qmd_timeout_seconds=int(os.getenv("QMD_TIMEOUT_SECONDS", "30")),
        qmd_refresh_command=os.getenv("QMD_REFRESH_COMMAND") or None,
        qmd_search_command=os.getenv("QMD_SEARCH_COMMAND") or None,
        llm_api_key=os.getenv("OPENAI_API_KEY") or None,
        llm_base_url=os.getenv("OPENAI_BASE_URL") or None,
        llm_model=os.getenv("LLM_MODEL") or None,
        llm_planner_command=os.getenv("LLM_PLANNER_COMMAND") or None,
        llm_planner_timeout_seconds=int(os.getenv("LLM_PLANNER_TIMEOUT_SECONDS", "30")),
        openxml_parser_src=_optional_path(os.getenv("OPENXML_PARSER_SRC", str(DEFAULT_OPENXML_PARSER_SRC))),
        extract_openxml_assets=os.getenv("EXTRACT_OPENXML_ASSETS", "true").lower()
        in {"1", "true", "yes", "on"},
        scan_interval_seconds=int(os.getenv("SCAN_INTERVAL_SECONDS", "300")),
        ingest_interval_seconds=int(os.getenv("INGEST_INTERVAL_SECONDS", "60")),
    )


def ensure_runtime_dirs(settings: Settings) -> None:
    for path in (
        settings.raw_sources_dir,
        settings.wiki_sources_dir,
        settings.agent_state_dir,
        settings.logs_dir,
        settings.locks_dir,
        settings.patches_dir,
        settings.config_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _parse_allowed_user_ids(value: str) -> set[int]:
    user_ids: set[int] = set()
    for item in value.replace(" ", "").split(","):
        if not item:
            continue
        user_ids.add(int(item))
    return user_ids


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)
