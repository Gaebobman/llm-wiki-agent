from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


Record = dict[str, Any]


def read_jsonl(path: Path) -> list[Record]:
    if not path.exists():
        return []
    records: list[Record] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}: expected object")
            records.append(value)
    return records


def append_jsonl(path: Path, record: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def rewrite_jsonl(path: Path, records: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def update_first(path: Path, predicate: Callable[[Record], bool], update: Record) -> Record | None:
    records = read_jsonl(path)
    updated: Record | None = None
    for record in records:
        if predicate(record):
            record.update(update)
            updated = record
            break
    if updated is not None:
        rewrite_jsonl(path, records)
    return updated
