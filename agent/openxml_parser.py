from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from agent.config import Settings
from agent.file_utils import safe_stem


@dataclass(frozen=True)
class OpenXmlParseResult:
    ok: bool
    markdown: str | None = None
    parser: str = "none"
    error: str | None = None


def parse_openxml(settings: Settings, raw_path: Path) -> OpenXmlParseResult:
    if raw_path.suffix.lower() != ".pptx":
        return OpenXmlParseResult(ok=False, error="unsupported openxml type")
    parser_src = settings.openxml_parser_src
    if parser_src is None or not parser_src.exists():
        return OpenXmlParseResult(ok=False, error=f"openxml-parser src not found: {parser_src}")
    _ensure_parser_path(parser_src)
    try:
        from document_inteligence.application.config import ParserConfig
        from document_inteligence.application.use_cases import ParseDocumentUseCase
        from document_inteligence.infrastructure.ingestors.pptx_ingestor import PptxIngestor
        from document_inteligence.infrastructure.verifiers.noop_caption_verifier import (
            NoopCaptionVerifier,
        )
    except Exception as exc:  # noqa: BLE001 - optional integration must fall back.
        return OpenXmlParseResult(ok=False, error=f"openxml-parser import failed: {exc}")

    try:
        config = ParserConfig()
        asset_dir = _asset_dir(settings, raw_path) if settings.extract_openxml_assets else None
        use_case = ParseDocumentUseCase(
            ingestors=[
                PptxIngestor(
                    asset_output_dir=str(asset_dir) if asset_dir is not None else None,
                    include_master_shapes=config.include_master_shapes,
                    deduplicate_master_shapes=config.deduplicate_master_shapes,
                )
            ],
            config=config,
            caption_verifier=NoopCaptionVerifier(),
        )
        parsed = use_case.execute(str(raw_path))
        markdown = use_case.to_markdown(parsed).strip()
        if not markdown:
            return OpenXmlParseResult(ok=False, parser="openxml-parser", error="empty markdown")
        return OpenXmlParseResult(ok=True, markdown=markdown, parser="openxml-parser")
    except Exception as exc:  # noqa: BLE001 - ingest should fall back to simple parser.
        return OpenXmlParseResult(ok=False, parser="openxml-parser", error=str(exc))


def _ensure_parser_path(parser_src: Path) -> None:
    parser_src_text = str(parser_src)
    if parser_src_text not in sys.path:
        sys.path.insert(0, parser_src_text)


def _asset_dir(settings: Settings, raw_path: Path) -> Path:
    return settings.wiki_sources_dir / safe_stem(raw_path)
