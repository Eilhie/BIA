# sync

Cross-domain workflow pages — grouped by *what the user is doing* (syncing/reconciling data) rather than by data domain, since each of these genuinely spans multiple domains rather than belonging to one.

## Key files

- **`1_Sync_dan_Transpose.py`** — Runs the full sync (robocopy from the server) + transpose (XLS → CSV/XLSX) pipeline from the browser, replacing `SYNC OMSHAR FAST.bat` + `AMBIL DATA BARU.bat` + `omset_pipeline/RUN.bat` for interactive use. Runs sync/transpose in a background thread/subprocess polled via `st.fragment`, specifically so the Cancel button stays responsive — a naive blocking loop would never register the click until the operation finished on its own.
- **`6_Cek_Cutoff_OMSHAR.py`** — Reads the cutoff date directly from each raw `.xls` file in `D:\DB OMSHAR\DB`, so you can see which brands are behind *before* running Transpose, not after.
- **`10_Atur_Gabungan_HOREKA.py`** / **`14_Atur_Gabungan_UMUM.py`** — Read-only status/contents of the Gabungan (merged-outlet) groups, sourced from Excel files owned by another division. Editing happens in those Excel files directly, never through this app.

## Notes

- None of these pages have a dedicated pipeline module of their own — they call into `core/omset_seeker.py`, `sku/sku_lookup.py`, and `omset_pipeline/transpose.py` directly.
