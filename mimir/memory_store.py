"""
memory_store.py (Mimir)
Shared read/write helpers for mimir/memory/ -- used by app.py (writing, via
the `catat:` chat flow and the Excel artifact uploader) and indexer.py
(reading, to embed every memory into the index). See memory/README.md for
the full convention this module implements.
"""

import re
from datetime import date
from pathlib import Path

import yaml

MEMORY_DIR = Path(__file__).resolve().parent / "memory"
INDEX_FILE = MEMORY_DIR / "MEMORY.md"

TYPE_DIRS = {
    "decision": "decisions",
    "correction": "corrections",
    "process": "processes",
    "artifact-structure": "artifacts",
    "artifact-purpose": "artifacts",
}


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "memory"


def _unique_path(mem_type: str, slug: str) -> Path:
    subdir = MEMORY_DIR / TYPE_DIRS[mem_type]
    suffix = "-structure" if mem_type == "artifact-structure" else "-purpose" if mem_type == "artifact-purpose" else ""
    base = f"{slug}{suffix}"
    path = subdir / f"{base}.md"
    n = 2
    while path.exists():
        path = subdir / f"{base}-{n}.md"
        n += 1
    return path


def save_memory(
    mem_type: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source_file: str | None = None,
) -> Path:
    """Writes one memory file with YAML frontmatter, appends one line to
    MEMORY.md, and returns the path written. Does not touch the Chroma
    index -- call indexer.add_single_chunk() separately so a save can be
    embedded immediately without a full rebuild."""
    if mem_type not in TYPE_DIRS:
        raise ValueError(f"Unknown memory type: {mem_type}")

    slug = slugify(title)
    path = _unique_path(mem_type, slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "name": path.stem,
        "type": mem_type,
        "tags": tags or [],
        "date": date.today().isoformat(),
    }
    if source_file:
        frontmatter["source_file"] = source_file

    body = (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + content.strip()
        + "\n"
    )
    path.write_text(body, encoding="utf-8")

    rel = path.relative_to(MEMORY_DIR.parent).as_posix()
    with INDEX_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- [{title}]({rel}) — {mem_type}\n")

    return path


def read_memory(path: Path) -> dict:
    """Parses one memory file's frontmatter + body. Raises if the file
    doesn't have valid `---`-delimited frontmatter -- a malformed memory
    file should fail loudly during indexing, not silently be skipped."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path} has no frontmatter")
    _, fm_text, body = text.split("---\n", 2)
    frontmatter = yaml.safe_load(fm_text) or {}
    return {"frontmatter": frontmatter, "body": body.strip(), "path": path}


def list_memories() -> list[dict]:
    """Every memory file under mimir/memory/, excluding MEMORY.md and
    README.md themselves."""
    memories = []
    for path in sorted(MEMORY_DIR.rglob("*.md")):
        if path.name in ("MEMORY.md", "README.md"):
            continue
        memories.append(read_memory(path))
    return memories
