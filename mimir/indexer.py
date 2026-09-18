"""
indexer.py (Mimir)
Builds Mimir's local doc-QA knowledge base: chunks the repo root README.md
plus every omset-app module's top-level docstring, embeds each chunk via
Ollama's nomic-embed-text (fully local, nothing leaves the machine), and
stores them in a persistent Chroma collection at mimir/.index/.

Run manually to (re)build the index:
    venv/Scripts/python.exe indexer.py
"""

import ast
from pathlib import Path

import chromadb
import ollama

REPO_ROOT = Path(__file__).resolve().parent.parent
OMSET_APP_DIR = REPO_ROOT / "omset-app"
README_PATH = REPO_ROOT / "README.md"
INDEX_DIR = Path(__file__).resolve().parent / ".index"
COLLECTION_NAME = "sda_wiki"
EMBED_MODEL = "nomic-embed-text"

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def chunk_text(text: str, source: str) -> list[dict]:
    """Simple fixed-size sliding-window chunker with overlap. Good enough
    for prose/docstrings -- no need for anything smarter at this scale."""
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append({"text": piece, "source": source})
        if end == n:
            break
        start = end - CHUNK_OVERLAP
    return chunks


def collect_module_docstrings() -> list[dict]:
    """Every .py file under omset-app/ with a non-trivial top-level
    docstring -- these already carry the rationale/history the user writes
    by hand (see e.g. bpr_pipeline.py, mclub_pipeline.py), which is exactly
    the kind of "why" a doc-QA index should answer from."""
    docs = []
    for path in sorted(OMSET_APP_DIR.rglob("*.py")):
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


def build_index() -> int:
    """Returns the number of chunks written."""
    all_chunks: list[dict] = []

    if README_PATH.exists():
        all_chunks.extend(chunk_text(README_PATH.read_text(encoding="utf-8"), "README.md"))

    for doc in collect_module_docstrings():
        all_chunks.extend(chunk_text(doc["text"], doc["source"]))

    if not all_chunks:
        raise RuntimeError("No chunks produced -- check REPO_ROOT/OMSET_APP_DIR paths")

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
        metadatas=[{"source": c["source"]} for c in all_chunks],
    )

    return len(all_chunks)


if __name__ == "__main__":
    count = build_index()
    print(f"Indexed {count} chunks into {INDEX_DIR}")
