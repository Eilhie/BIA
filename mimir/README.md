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
- ✅ Looks up real outlet data by calling Heimdall's own functions (`tools.py` → `core.omset_seeker`): `cari_outlet` (omset per brand per month for a site number) and `cari_nama_outlet` (find a site number from part of an outlet name). `cari_outlet`'s result renders in the 🔧 panel using Heimdall's own `core/render_outlet_image.build_html_table()` — the same report layout as the Omset Seeker page — instead of a plain dataframe or the LLM's prose, so what you see is the real report, not a paraphrase of it. `cari_nama_outlet` still shows a plain table (search results, not a single outlet's report).
- ✅ **Copy / Print / Download** the outlet report, same as Heimdall's Omset Seeker page — reuses that page's own battle-tested JS (clipboard API with a LAN-safe fallback, print via a Blob-URL `<a>` instead of `window.open()`) and PNG generation (`render_outlet_report`), not a reimplementation.
- 🔒 **Scope is outlet lookup only, on purpose.** Heimdall gates SKU-claim/dashboard data behind Admin login; Mimir has no login, so exposing those here would silently bypass that gate. Widening `tools.py` means deciding the access-control question first.
- ⚠️ **Known limits of tool use** (7–8B local models): a model can still misread a table or paraphrase a brand name wrongly even when the tool result is correct — check the 🔧 panel for anything important. `cari_outlet` pre-computes the latest month and per-brand values for exactly this reason. It only does lookups; it can't compute totals, compare outlets, or touch anything Heimdall writes.

## Environment notes

- Own isolated `venv/`, created with `--system-site-packages` so `pandas`/`streamlit`/`numpy` are inherited from the global Python install (already trusted by Windows after months of production use) rather than re-installed as fresh copies — a fresh native-extension package in a brand-new venv can trigger a Windows Application Control / Smart App Control scan that isn't guaranteed to clear quickly.
- Model: `qwen3:8b`, plus `nomic-embed-text` for embeddings. History: started with `hermes3:8b` + `qwen2.5:7b-instruct`; Qwen won that round (chained lookups 3/3 vs 1/3, "site not found" relayed 3/3 vs 0/3) so Hermes was dropped. `qwen3:8b` was then tested against `deepseek-r1:8b` as a second-generation upgrade: Qwen3 matched or beat Qwen2.5 on every axis, so both older models were removed. DeepSeek-R1 was removed after a clear failure — it never called the tool for a direct data request (0/3), instead **fabricating an empty template mimicking the tool's own output labels** ("BULAN TERAKHIR", "Nilai per brand di bulan terakhir") with no real data behind it, worse than simply refusing. Recorded as a Mimir memory (`decisions/`) for the full numbers.
- Ollama is confirmed bound to `127.0.0.1:11434` only — verify with `netstat -ano | findstr 11434` if in doubt.
