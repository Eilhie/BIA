# bpr

Python replica of the "BPR BIA DAILY TEMPLATE.xlsx" report (NORM/STOK/DOI/Order rollups per Depo and per Wilayah), which used to require manual SUMIFS/AVERAGEIFS formulas plus an external Excel link that had to be manually relinked every morning — easy to forget, silently producing stale numbers.

## Key files

- **`bpr_pipeline.py`** — All the calculation logic, verified cell-by-cell against a cached template snapshot (see `test_bpr_pipeline.py`), not guessed. Reads the daily raw file directly from Google Drive (the real authoritative source, arrives automatically ~07:00 including weekends), falling back to a local archive copy if Google Drive isn't mounted. Every file read from Drive is also copied back into the local working folder automatically, closing a gap where the previous manual process often skipped weekends.
- **`render_bpr.py`** — HTML/Excel/PDF rendering, matching the original template's colors, merged headers, fonts, and number formats exactly (verified against real `openpyxl` cell properties, not assumptions).
- **`13_BPR.py`** — The page.

## Notes

- Recomputed from scratch every time the page opens — there's no cached/stale state to worry about, unlike the manual external-link workflow it replaces.
- One column present in the original template (`Rekap Per WILAYAH`'s unlabeled column F) is a known copy-paste artifact with a broken formula reference — intentionally not replicated here.
