from __future__ import annotations

from dataclasses import dataclass

from agent.config import Settings, load_settings


@dataclass(frozen=True)
class QmdResult:
    ok: bool
    message: str


def refresh_changed(settings: Settings) -> QmdResult:
    return QmdResult(
        ok=True,
        message=f"qmd refresh stub invoked with config {settings.qmd_config}",
    )


def search(settings: Settings, query: str, mode: str = "local") -> dict:
    return {
        "query": query,
        "mode": mode,
        "results": [],
        "message": "qmd search stub; real CLI/API integration is planned for Phase 6",
        "config": str(settings.qmd_config),
    }


def main() -> None:
    print(refresh_changed(load_settings()).message)


if __name__ == "__main__":
    main()
