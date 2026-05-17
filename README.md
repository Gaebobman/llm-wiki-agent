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

## User Manual

### 1. Update The Project

Update the checkout and submodule:

```bash
cd /home/standard/0_Code/llm-wiki-agent
git pull
git submodule update --init --recursive
```

### 2. Prepare Runtime Directories

Create the runtime directories used by the agent:

```bash
mkdir -p /home/standard/llm-wiki-data/vault/raw/sources
mkdir -p /home/standard/llm-wiki-data/agent-state
mkdir -p /home/standard/llm-wiki-data/config
```

Use these minimum environment variables for local CLI testing:

```bash
export WIKI_ROOT=/home/standard/llm-wiki-data/vault
export AGENT_STATE_DIR=/home/standard/llm-wiki-data/agent-state
export CONFIG_DIR=/home/standard/llm-wiki-data/config
export OPENXML_PARSER_SRC=/home/standard/0_Code/llm-wiki-agent/vendor/openxml-parser/src
```

Configure an OpenAI-compatible LLM endpoint for semantic planning:

```bash
export OPENAI_BASE_URL=http://host.docker.internal:8000/v1
export OPENAI_API_KEY=sk-dummy
export LLM_MODEL=qwen3.5-27b
export LLM_PLANNER_TIMEOUT_SECONDS=30
```

Configure Telegram if you want to operate the agent through chat:

```bash
export TELEGRAM_BOT_TOKEN=123456:xxxx
export TELEGRAM_ALLOWED_USER_IDS=123456789
```

### 3. Run The Agent Locally

Check the current agent status:

```bash
python3.12 -m agent.main --once status
```

Start the normal polling loop:

```bash
python3.12 -m agent.main
```

If `TELEGRAM_BOT_TOKEN` is configured, this starts Telegram polling. If not, the
agent runs the scanner/ingest loop.

### 4. Add Source Documents

Put files under `raw/sources`:

```bash
cp README.md /home/standard/llm-wiki-data/vault/raw/sources/readme-test.md
```

Then scan and ingest:

```bash
python -m agent.main --once scan
python -m agent.main --once queue
python -m agent.main --once ingest
```

Generated source notes are written to:

```text
/home/standard/llm-wiki-data/vault/wiki/sources
```

The wiki index and log are updated at:

```text
/home/standard/llm-wiki-data/vault/wiki/index.md
/home/standard/llm-wiki-data/vault/wiki/log.md
```

PPTX files use `vendor/openxml-parser` when available:

```bash
cp vendor/openxml-parser/public_samples/openxml_parser_public_sample.pptx \
  /home/standard/llm-wiki-data/vault/raw/sources/
python -m agent.main --once scan
python -m agent.main --once ingest
```

### 5. Search And Route

```bash
python -m agent.main --once local "research contract"
python -m agent.main --once global "research contract"
python -m agent.main --once route "research contract"
```

### 6. Update Wiki Notes

Update requests are patch-first. The agent creates a patch under
`agent-state/patches/{patch_id}` and waits for approval before changing wiki
Markdown.

```bash
python -m agent.main --once update "openxml parser 문서에 PPTX 이미지 추출 정책을 보강해줘"
python -m agent.main --once patches
```

Apply a normal patch:

```bash
python -m agent.main --once apply PATCH_ID
```

High-risk patches require a second approval step:

```bash
python -m agent.main --once approve PATCH_ID
python -m agent.main --once apply PATCH_ID
```

Reject a patch:

```bash
python -m agent.main --once reject PATCH_ID
```

Inspect conflicts and logs:

```bash
python -m agent.main --once conflicts
python -m agent.main --once logs
```

### 7. Run With Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f llm-wiki-agent
```

One-shot Docker commands are useful for checks:

```bash
docker compose run --rm llm-wiki-agent python -m agent.main --once status
```

### 8. Telegram Commands

Available Telegram commands:

```text
/status
/scan
/queue
/ingest
/bases
/local <query>
/global <query>
/search <query>
/route <query>
/update <request>
/approve <patch_id>
/apply <patch_id>
/reject <patch_id>
/patches
/conflicts
/logs
```

You can also upload a document to the Telegram bot. The agent stores it under
`raw/sources`, queues it, and keeps the raw source immutable.

### 9. Health Check

For local validation:

```bash
source .venv/bin/activate
python -m pytest
docker compose run --rm llm-wiki-agent python -m agent.main --once status
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
