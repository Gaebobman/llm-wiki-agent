# LLM-Wiki Agent

MVP implementation for a Jetson-hosted wiki agent that watches an Obsidian vault,
queues new raw source files, creates source notes, and exposes a small Telegram
command surface.

See `docs/README.md` for development direction, features, and Mermaid flow diagrams.

The current implementation covers the Phase 1-4 ingest MVP plus selected search, Bases, and upload features from later phases:

- rclone sync script scaffold
- Docker/runtime scaffold
- raw source scanner
- JSONL manifest and ingest queue
- source note ingest worker
- Telegram polling commands for status, scan, queue, ingest, Bases, search routing, and document upload
- qmd CLI integration with fallback Markdown search
- Obsidian Bases search-routing file generation
- PPTX ingest via `vendor/doc-xml-parser` core parser when available

Python 3.12 or newer is required. The Docker image uses Python 3.12.

## Local smoke commands

```bash
python3.12 -m agent.main --once status
python3.12 -m agent.main --once scan
python3.12 -m agent.main --once ingest
python3.12 -m agent.main --once bases
python3.12 -m agent.main --once route "research contract"
python3.12 -m agent.main --once update "RAG 토픽 문서에 qmd 검색 라우팅 내용 추가해줘"
python3.12 -m agent.main --once patches
python3.12 -m agent.main --once conflicts
python3.12 -m agent.main --once logs
```

Set these environment variables when running outside Docker:

```bash
export WIKI_ROOT=/home/standard/llm-wiki-data/vault
export AGENT_STATE_DIR=/home/standard/llm-wiki-data/agent-state
export CONFIG_DIR=/home/standard/llm-wiki-data/config
export DOC_XML_PARSER_SRC=/home/standard/0_Code/llm-wiki-agent/vendor/doc-xml-parser/src
```

## Submodules

This repository uses `vendor/doc-xml-parser` as a Git submodule.

Clone with:

```bash
git clone --recurse-submodules https://github.com/Gaebobman/llm-wiki-agent.git
```

For an existing clone:

```bash
git submodule update --init --recursive
```

Docker copies `vendor/doc-xml-parser` into the image and sets
`DOC_XML_PARSER_SRC=/app/vendor/doc-xml-parser/src`.
