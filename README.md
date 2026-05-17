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
- PPTX ingest via `vendor/openxml-parser` core parser when available
- LLM-planner update workflow with policy checks, conflicts, approve/apply/reject, and logs

Python 3.12 or newer is required. The Docker image uses Python 3.12.

## Local smoke commands

```bash
python3.12 -m agent.main --once status
python3.12 -m agent.main --once scan
python3.12 -m agent.main --once ingest
python3.12 -m agent.main --once bases
python3.12 -m agent.main --once route "research contract"
python3.12 -m agent.main --once update "RAG 토픽 문서에 qmd 검색 라우팅 내용 추가해줘"
python3.12 -m agent.main --once approve "patch_id"
python3.12 -m agent.main --once apply "patch_id"
python3.12 -m agent.main --once patches
python3.12 -m agent.main --once conflicts
python3.12 -m agent.main --once logs
```

Set these environment variables when running outside Docker:

```bash
export WIKI_ROOT=/home/standard/llm-wiki-data/vault
export AGENT_STATE_DIR=/home/standard/llm-wiki-data/agent-state
export CONFIG_DIR=/home/standard/llm-wiki-data/config
export OPENXML_PARSER_SRC=/home/standard/0_Code/llm-wiki-agent/vendor/openxml-parser/src
# Optional: use OPENAI_BASE_URL + LLM_MODEL directly, or provide a command that
# reads planner JSON from stdin and returns planner JSON on stdout.
export LLM_PLANNER_COMMAND=/home/standard/llm-wiki-data/config/planner-wrapper.sh
```

## Submodules

This repository uses `vendor/openxml-parser` as a Git submodule.

Clone with:

```bash
git clone --recurse-submodules https://github.com/Gaebobman/llm-wiki-agent.git
```

For an existing clone:

```bash
git submodule update --init --recursive
```

Docker copies `vendor/openxml-parser` into the image and sets
`OPENXML_PARSER_SRC=/app/vendor/openxml-parser/src`.

## Safety

CRUD-style update requests use a patch-first workflow. The agent writes
`before.md`, `after.md`, `diff.patch`, and `metadata.json` under
`agent-state/patches/{patch_id}` first. It only changes wiki Markdown after an
explicit `/apply {patch_id}`.

The request planner is schema-driven. When `OPENAI_BASE_URL` and `LLM_MODEL` are
configured, the agent uses an OpenAI-compatible chat endpoint to classify the
request semantically. `LLM_PLANNER_COMMAND` can override that with a local
command that reads planner JSON on stdin and returns planner JSON on stdout. The
planner output includes fields such as `crud_action`, `destructive_action`,
`risk_level`, `local_query`, `global_query`, and `rationale`. If no planner is
configured, the fallback only uses command context, for example `/update` means a
mutation proposal, and avoids language keyword decisions.

`agent.policies` blocks update targets outside `WIKI_ROOT/wiki`, blocks raw-file
targets, requires Markdown targets, and uses the planner's `risk_level` and
`destructive_action` to enforce approval gates. High-risk patches require a
second `/approve {patch_id}` step before `/apply {patch_id}`.
