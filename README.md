# LLM-Wiki Agent

MVP implementation for a Jetson-hosted wiki agent that watches an Obsidian vault,
queues new raw source files, creates source notes, and exposes a small Telegram
command surface.

See `docs/README.md` for development direction, features, and Mermaid flow diagrams.

The current implementation covers Phase 1-4 from `plan/initial_plan.md`:

- rclone sync script scaffold
- Docker/runtime scaffold
- raw source scanner
- JSONL manifest and ingest queue
- source note ingest worker
- Telegram polling commands for status, scan, queue, and ingest
- qmd refresh/search stub interface

Python 3.12 or newer is required. The Docker image uses Python 3.12.

## Local smoke commands

```bash
python3.12 -m agent.main --once status
python3.12 -m agent.main --once scan
python3.12 -m agent.main --once ingest
```

Set these environment variables when running outside Docker:

```bash
export WIKI_ROOT=/home/standard/llm-wiki-data/vault
export AGENT_STATE_DIR=/home/standard/llm-wiki-data/agent-state
export CONFIG_DIR=/home/standard/llm-wiki-data/config
```
