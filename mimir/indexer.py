"""
indexer.py (Mimir)
Builds Mimir's local doc-QA knowledge base from three sources: the repo
root README.md + every heimdall module's top-level docstring (the
original doc-QA index), mimir/memory/ (decisions/corrections/processes/
artifacts captured via the `catat:` chat flow or the Excel uploader), and
Claude Code's own pre-existing memory files for this project (a separate,
already-rich knowledge base built up across prior sessions -- read-only,
not duplicated into mimir/memory/, so each memory system keeps a single
source of truth). Every chunk is embedded via Ollama's nomic-embed-text
(fully local, nothing leaves the machine) and stored in a persistent
Chroma collection at mimir/.index/.

Run manually to (re)build the index:
    venv/Scripts/python.exe indexer.py
"""

import ast
from pathlib import Path

import chromadb
import ollama
import yaml

import memory_store

REPO_ROOT = Path(__file__).resolve().parent.parent
HEIMDALL_DIR = REPO_ROOT / "heimdall"
README_PATH = REPO_ROOT / "README.md"
INDEX_DIR = Path(__file__).resolve().parent / ".index"
COLLECTION_NAME = "sda_wiki"
EMBED_MODEL = "nomic-embed-text"

# Claude Code's own memory store for this project -- see memory_store.py's
# module docstring / mimir/memory/README.md for why this is read, not copied.
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "d--SDAAREA" / "memory"

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def chunk_text(text: str, source: str, **extra_meta) -> list[dict]:
    """Simple fixed-size sliding-window chunker with overlap. Good enough
    for prose/docstrings -- no need for anything smarter at this scale."""
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append({"text": piece, "source": source, **extra_meta})
        if end == n:
            break
        start = end - CHUNK_OVERLAP
    return chunks


def collect_module_docstrings() -> list[dict]:
    """Every .py file under heimdall/ with a non-trivial top-level
    docstring -- these already carry the rationale/history the user writes
    by hand (see e.g. bpr_pipeline.py, mclub_pipeline.py), which is exactly
    the kind of "why" a doc-QA index should answer from."""
    docs = []
    for path in sorted(HEIMDALL_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        doc = ast.get_docstring(tree)
        if doc and len(doc.strip()) > 40:  # skip trivial one-liners
            rel = path.relative_to(REPO_ROOT).as_posix()
            docs.append({"text": doc.strip(), "source": rel})
    return docs


def collect_memories() -> list[dict]:
    """Every memory Mimir itself has captured (mimir/memory/), via
    `catat:` in chat or the Excel artifact uploader. See
    mimir/memory/README.md for the format."""
    docs = []
    for mem in memory_store.list_memories():
        fm = mem["frontmatter"]
        rel = mem["path"].relative_to(REPO_ROOT).as_posix()
        docs.append({
            "text": mem["body"],
            "source": rel,
            "kind": "memory",
            "mem_type": fm.get("type", "unknown"),
        })
    return docs


def collect_claude_memories() -> list[dict]:
    """Claude Code's own pre-existing memory files for this project --
    checked defensively since this lives outside the repo and outside
    Mimir's own control (a different machine/session layout could lack
    it entirely; that's fine, just skip rather than fail the whole index)."""
    docs = []
    if not CLAUDE_MEMORY_DIR.is_dir():
        return docs
    for path in sorted(CLAUDE_MEMORY_DIR.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        try:
            mem = memory_store.read_memory(path)
        except yaml.YAMLError:
            # Some of these files predate consistent use of yaml.safe_dump()
            # for writing, so a double-quoted value can contain a literal
            # Windows path ("D:\EAO...") that YAML tries to interpret as an
            # escape sequence. Retry once by doubling backslashes -- these
            # frontmatter fields are just name/description/metadata, never
            # real escape sequences, so this is safe rather than a hack
            # that could silently corrupt genuine content.
            try:
                text = path.read_text(encoding="utf-8")
                _, fm_text, body = text.split("---\n", 2)
                fixed_fm = fm_text.replace("\\", "\\\\")
                frontmatter = yaml.safe_load(fixed_fm) or {}
                mem = {"frontmatter": frontmatter, "body": body.strip(), "path": path}
            except (ValueError, yaml.YAMLError) as e:
                print(f"  [skip] {path.name}: {e}")
                continue
        except ValueError:
            continue  # no frontmatter at all -- not a memory file we can read
        fm = mem["frontmatter"]
        metadata = fm.get("metadata") or {}
        docs.append({
            "text": mem["body"],
            "source": f"claude-memory/{path.name}",
            "kind": "claude_memory",
            "mem_type": metadata.get("type", "unknown"),
        })
    return docs


def build_index() -> int:
    """Returns the number of chunks written."""
    all_chunks: list[dict] = []

    if README_PATH.exists():
        all_chunks.extend(chunk_text(README_PATH.read_text(encoding="utf-8"), "README.md", kind="doc"))

    for doc in collect_module_docstrings():
        all_chunks.extend(chunk_text(doc["text"], doc["source"], kind="doc"))

    for doc in collect_memories():
        all_chunks.extend(chunk_text(doc["text"], doc["source"], kind=doc["kind"], mem_type=doc["mem_type"]))

    for doc in collect_claude_memories():
        all_chunks.extend(chunk_text(doc["text"], doc["source"], kind=doc["kind"], mem_type=doc["mem_type"]))

    if not all_chunks:
        raise RuntimeError("No chunks produced -- check REPO_ROOT/HEIMDALL_DIR paths")

    embeddings = []
    for chunk in all_chunks:
        resp = ollama.embed(model=EMBED_MODEL, input=chunk["text"])
        embeddings.append(resp["embeddings"][0])

    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # first run, nothing to delete
    collection = client.create_collection(COLLECTION_NAME)

    collection.add(
        ids=[f"chunk-{i}" for i in range(len(all_chunks))],
        embeddings=embeddings,
        documents=[c["text"] for c in all_chunks],
        metadatas=[_clean_metadata(c) for c in all_chunks],
    )

    return len(all_chunks)


def _clean_metadata(chunk: dict) -> dict:
    """Chroma metadata values must be str/int/float/bool -- drop the
    'text' key (that's the document itself, not metadata) and keep
    everything else as-is (source/kind/mem_type are all already strings)."""
    return {k: v for k, v in chunk.items() if k != "text"}


def add_single_chunk(text: str, source: str, kind: str, mem_type: str | None = None) -> None:
    """Embeds and adds ONE chunk to the existing index immediately --
    used right after a `catat:` save or an Excel artifact upload, so the
    new memory is searchable without forcing a full rebuild (which would
    also needlessly re-embed everything else that hasn't changed)."""
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    collection = client.get_or_create_collection(COLLECTION_NAME)

    embedding = ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]
    metadata = {"source": source, "kind": kind}
    if mem_type:
        metadata["mem_type"] = mem_type

    # Unique id: count of existing items is good enough here since ids are
    # never reused (this store is append-only outside of a full rebuild).
    next_id = collection.count()
    collection.add(
        ids=[f"chunk-live-{next_id}"],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata],
    )


if __name__ == "__main__":
    count = build_index()
    print(f"Indexed {count} chunks into {INDEX_DIR}")
