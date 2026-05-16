from __future__ import annotations

from pathlib import Path

from agent.config import Settings, load_settings


SEARCH_ROUTING_BASE = """\
filters:
  or:
    - file.inFolder("wiki/sources")
    - file.inFolder("wiki/entities")
    - file.inFolder("wiki/topics")
    - file.inFolder("wiki/analyses")

properties:
  file.name:
    displayName: File
  type:
    displayName: Type
  status:
    displayName: Status
  review_state:
    displayName: Review State
  retrieval_scope:
    displayName: Retrieval Scope
  source_files:
    displayName: Source Files
  local_keys:
    displayName: Local Keys
  global_topics:
    displayName: Global Topics
  aliases:
    displayName: Aliases
  evidence_level:
    displayName: Evidence Level
  file.links:
    displayName: Links
  file.backlinks:
    displayName: Backlinks

views:
  - type: table
    name: Local Candidates
    limit: 50
    filters:
      or:
        - file.inFolder("wiki/entities")
        - file.inFolder("wiki/sources")
        - 'retrieval_scope == "local"'
        - 'retrieval_scope == "hybrid"'
    order:
      - file.name
      - type
      - status
      - review_state
      - updated
      - source_files
      - aliases
      - local_keys
      - file.links
      - file.backlinks

  - type: table
    name: Global Candidates
    limit: 50
    filters:
      or:
        - file.inFolder("wiki/topics")
        - file.inFolder("wiki/analyses")
        - 'retrieval_scope == "global"'
        - 'retrieval_scope == "hybrid"'
    order:
      - file.name
      - type
      - status
      - review_state
      - updated
      - source_files
      - global_topics
      - retrieval_scope
      - file.links
      - file.backlinks

  - type: table
    name: Hybrid Review
    limit: 100
    filters:
      or:
        - 'retrieval_scope == "hybrid"'
        - 'source_files != null'
        - file.inFolder("wiki/analyses")
    order:
      - file.name
      - type
      - retrieval_scope
      - status
      - review_state
      - updated
      - source_files
      - local_keys
      - global_topics
      - aliases
      - file.links
      - file.backlinks
      - evidence_level
"""


def search_routing_base_path(settings: Settings) -> Path:
    return settings.wiki_root / "wiki" / "bases" / "search-routing.base"


def ensure_search_routing_base(settings: Settings, overwrite: bool = False) -> Path:
    path = search_routing_base_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not path.exists():
        path.write_text(SEARCH_ROUTING_BASE, encoding="utf-8")
    return path


def main() -> None:
    path = ensure_search_routing_base(load_settings())
    print(f"search routing base ready: {path}")


if __name__ == "__main__":
    main()
