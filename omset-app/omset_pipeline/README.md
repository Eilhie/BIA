# omset_pipeline

The heart of the data pipeline: turns raw per-SKU OMSHAR `.xls` files (synced from the company server) into the per-brand CSV/XLSX outputs every other app queries.

## Key files

- **`transpose.py`** — Stacks the raw per-SKU sheets for each brand into unified DAPUL/LAPUL/HOREKA outputs (one CSV + one XLSX per brand), running brands in parallel via `multiprocessing.Pool`. Also maintains the `SKU_RAW` cache used by the per-SKU lookup tools. Brand-to-file mappings (`UMUM_FILE`, `HOREKA_FILE`, `HOREKA_KEG_FILE`) live here, including derived blend brands (e.g. `BIR PROST`, `BIR MIX`, `TOTAL KEG`) that combine several official brands' files without being separately synced.
- **`gabungan_live_generator.py`** — When only the legacy "Toko Gabungan Update ..." format is available for a month, builds a "Formula Live" equivalent with live VLOOKUP formulas, matching the format another division normally provides.
- **`sql_cache.py`** — An optional SQLite-backed fast path for outlet queries. Currently a prototype: not wired into `omset_seeker.py` or any page yet.
- **`RUN.bat`** — Standalone launcher for `transpose.py`, independent of the Streamlit app.

## Notes

- Output lands in `omset_pipeline/output/` (CSV, XLSX, IMAGE, GABUNGAN_LIVE, SQL_CACHE subfolders) — all gitignored, regenerated from source data.
- `transpose.py`'s own default DB source (`D:\SDAAREA\...\DB`) is intentionally always empty as a nominal fallback — the real synced data lives at `D:\DB OMSHAR\DB` (see `core/paths.py`'s `OMSHAR_DB_DIR`).
