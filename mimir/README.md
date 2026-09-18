# Mimir

**Codename: Mimir** — the Norse keeper of wisdom, whose counsel could always be sought even after everything else was gone. This app exists for the same reason: the "why" behind this codebase's decisions currently lives only in scattered code comments and one person's memory — Mimir makes it something anyone can ask, in plain language, at any time.

A local-only Wiki LLM: retrieval-augmented Q&A over `heimdall`'s `README.md` and every module's docstrings, answered by a locally-run LLM (via [Ollama](https://ollama.com)). Nothing — not the questions, not the documentation, not the answers — ever leaves this machine.

## Running it

Double-click `run.bat`, or manually:

```
venv\Scripts\python.exe -m streamlit run app.py --server.port 8600
```

Opens at `http://localhost:8600`.

## How it works

1. **`indexer.py`** — chunks the repo's `README.md` + every `heimdall` module's top-level docstring, embeds each chunk locally via Ollama's `nomic-embed-text`, and stores them in a Chroma vector database at `.index/` (gitignored — rebuild anytime with the sidebar's "Bangun ulang index" button, or `venv/Scripts/python.exe indexer.py`).
2. **`app.py`** — the chat UI. On each question, it embeds the question, retrieves the most relevant indexed chunks, and asks a local LLM to answer using only that retrieved context — never inventing anything the docs don't say.

## Current capability

- ✅ Answers "how does X work" / "why is Y done this way" questions, grounded in real docs, with sources shown under every answer.
- ❌ Cannot yet answer questions about live data (e.g. "what's the omset for outlet X") — it's explicitly instructed to say so rather than invent a number. Real-data lookups (calling `omset_seeker`/`sku_lookup` directly) are planned next.

## Environment notes

- Own isolated `venv/`, created with `--system-site-packages` so `pandas`/`streamlit`/`numpy` are inherited from the global Python install (already trusted by Windows after months of production use) rather than re-installed as fresh copies — a fresh native-extension package in a brand-new venv can trigger a Windows Application Control / Smart App Control scan that isn't guaranteed to clear quickly.
- Models used: `hermes3:8b` and `qwen2.5:7b-instruct` (switchable in the sidebar, for an ongoing side-by-side comparison — no default has been picked yet), plus `nomic-embed-text` for embeddings.
- Ollama is confirmed bound to `127.0.0.1:11434` only — verify with `netstat -ano | findstr 11434` if in doubt.
