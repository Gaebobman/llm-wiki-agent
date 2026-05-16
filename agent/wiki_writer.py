from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from agent.config import Settings
from agent.file_utils import is_probably_text, relative_to_root, safe_stem
from agent.timeutils import today


def source_note_path(settings: Settings, raw_rel_path: str) -> Path:
    return settings.wiki_sources_dir / f"{safe_stem(Path(raw_rel_path))}.md"


def build_source_note(settings: Settings, raw_rel_path: str, sha256: str, ingest_source: str) -> str:
    raw_path = settings.wiki_root / raw_rel_path
    title = Path(raw_rel_path).stem.replace("-", " ").replace("_", " ").strip() or Path(raw_rel_path).name
    content = _extract_body(raw_path)
    date = today()
    return "\n".join(
        [
            "---",
            f"title: {title}",
            "type: source",
            "status: active",
            f"created: {date}",
            f"updated: {date}",
            "source_files:",
            f"  - {raw_rel_path}",
            f"ingest_source: {ingest_source}",
            f"source_hash: {sha256}",
            "retrieval_scope: local",
            "review_state: draft",
            "evidence_level: parsed",
            "---",
            "",
            f"# {title}",
            "",
            "## Source",
            "",
            f"- Raw file: `{raw_rel_path}`",
            f"- SHA256: `{sha256}`",
            f"- Ingest source: `{ingest_source}`",
            "",
            "## Extracted Content",
            "",
            content,
            "",
        ]
    )


def write_source_note(settings: Settings, raw_rel_path: str, sha256: str, ingest_source: str) -> Path:
    note_path = source_note_path(settings, raw_rel_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        build_source_note(settings, raw_rel_path, sha256, ingest_source),
        encoding="utf-8",
    )
    return note_path


def append_index_entry(settings: Settings, note_path: Path, raw_rel_path: str) -> None:
    settings.wiki_index_path.parent.mkdir(parents=True, exist_ok=True)
    rel_note = relative_to_root(note_path, settings.wiki_root)
    entry = f"- [[{rel_note.removesuffix('.md')}]] from `{raw_rel_path}`"
    if settings.wiki_index_path.exists():
        existing = settings.wiki_index_path.read_text(encoding="utf-8")
    else:
        existing = "# Wiki Index\n\n## Sources\n\n"
    if entry in existing:
        return
    if "## Sources" not in existing:
        existing = existing.rstrip() + "\n\n## Sources\n\n"
    settings.wiki_index_path.write_text(existing.rstrip() + "\n" + entry + "\n", encoding="utf-8")


def append_log_entry(settings: Settings, raw_rel_path: str, note_path: Path, sha256: str, source: str) -> None:
    settings.wiki_log_path.parent.mkdir(parents=True, exist_ok=True)
    rel_note = relative_to_root(note_path, settings.wiki_root)
    date_heading = f"## {today()}"
    if settings.wiki_log_path.exists():
        existing = settings.wiki_log_path.read_text(encoding="utf-8")
    else:
        existing = "# Wiki Log\n\n"
    entry = "\n".join(
        [
            f"- Ingested `{raw_rel_path}`",
            f"  - Created `{rel_note}`",
            f"  - Source: {source}",
            f"  - Hash: `{sha256}`",
            "  - qmd index refresh requested",
        ]
    )
    if entry in existing:
        return
    if date_heading not in existing:
        existing = existing.rstrip() + f"\n\n{date_heading}\n\n"
    settings.wiki_log_path.write_text(existing.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def _extract_body(raw_path: Path) -> str:
    if not raw_path.exists():
        return "_Raw source file is missing at ingest time._"
    extracted = _extract_structured_document(raw_path)
    if extracted is not None:
        return extracted
    if not is_probably_text(raw_path):
        return (
            "_No text extractor is available for this binary file yet. The raw file has "
            "been registered as a source note for later parser expansion._"
        )
    try:
        text = raw_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = raw_path.read_text(encoding="utf-8", errors="replace")
    if raw_path.suffix.lower() in {".md", ".markdown"}:
        return text.strip() or "_No text content extracted._"
    suffix = raw_path.suffix.lower().lstrip(".") or "text"
    return f"```{suffix}\n{text.rstrip()}\n```"


def _extract_structured_document(raw_path: Path) -> str | None:
    suffix = raw_path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(raw_path)
    if suffix == ".docx":
        return _extract_docx(raw_path)
    if suffix == ".pptx":
        return _extract_pptx(raw_path)
    if suffix == ".xlsx":
        return _extract_xlsx(raw_path)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        return _extract_image_ocr(raw_path)
    return None


def _extract_pdf(raw_path: Path) -> str | None:
    if shutil.which("pdftotext") is None:
        return None
    result = subprocess.run(
        ["pdftotext", "-layout", str(raw_path), "-"],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _extract_docx(raw_path: Path) -> str | None:
    with _open_zip(raw_path) as archive:
        if archive is None:
            return None
        xml = _read_zip_text(archive, "word/document.xml")
    if not xml:
        return None
    paragraphs = _paragraph_text(xml)
    return "\n\n".join(paragraphs) if paragraphs else None


def _extract_pptx(raw_path: Path) -> str | None:
    with _open_zip(raw_path) as archive:
        if archive is None:
            return None
        slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide"))
        slides: list[str] = []
        for index, name in enumerate(slide_names, start=1):
            xml = _read_zip_text(archive, name)
            if not xml:
                continue
            text = "\n".join(_all_text_nodes(xml))
            if text.strip():
                slides.append(f"## Slide {index}\n\n{text.strip()}")
    return "\n\n".join(slides) if slides else None


def _extract_xlsx(raw_path: Path) -> str | None:
    with _open_zip(raw_path) as archive:
        if archive is None:
            return None
        shared_strings = _xlsx_shared_strings(archive)
        sheet_names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))
        sheets: list[str] = []
        for index, name in enumerate(sheet_names, start=1):
            xml = _read_zip_text(archive, name)
            if not xml:
                continue
            rows = _xlsx_rows(xml, shared_strings)
            if rows:
                table = "\n".join(" | ".join(cell for cell in row) for row in rows)
                sheets.append(f"## Sheet {index}\n\n```text\n{table}\n```")
    return "\n\n".join(sheets) if sheets else None


def _extract_image_ocr(raw_path: Path) -> str | None:
    if shutil.which("tesseract") is None:
        return None
    result = subprocess.run(
        ["tesseract", str(raw_path), "stdout", "-l", "kor+eng"],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False


def _open_zip(path: Path):
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return _NullContext()


def _read_zip_text(archive: zipfile.ZipFile, name: str) -> str | None:
    try:
        return archive.read(name).decode("utf-8")
    except KeyError:
        return None


def _paragraph_text(xml: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return paragraphs


def _all_text_nodes(xml: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []
    return [node.text.strip() for node in root.iter() if node.tag.endswith("}t") and node.text]


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    xml = _read_zip_text(archive, "xl/sharedStrings.xml")
    if not xml:
        return []
    return _all_text_nodes(xml)


def _xlsx_rows(xml: str, shared_strings: list[str]) -> list[list[str]]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []
    rows: list[list[str]] = []
    for row in root.iter():
        if not row.tag.endswith("}row"):
            continue
        values: list[str] = []
        for cell in row:
            if not cell.tag.endswith("}c"):
                continue
            value_node = next((child for child in cell if child.tag.endswith("}v")), None)
            raw_value = value_node.text if value_node is not None else ""
            if cell.attrib.get("t") == "s" and raw_value.isdigit():
                index = int(raw_value)
                values.append(shared_strings[index] if index < len(shared_strings) else raw_value)
            else:
                values.append(raw_value or "")
        if any(value.strip() for value in values):
            rows.append(values)
    return rows
