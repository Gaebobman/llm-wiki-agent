from __future__ import annotations

import hashlib
import re
from pathlib import Path


TEXT_EXTENSIONS = {
    ".csv",
    ".log",
    ".md",
    ".markdown",
    ".rst",
    ".text",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    stem = re.sub(r"[^a-z0-9가-힣._-]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-._")
    return stem or "source"


def relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_probably_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS
