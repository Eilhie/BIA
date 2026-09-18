# cukai

Estimates competitor sales volume from excise/tax (cukai) data — the only available proxy for competitor volume, since their actual sales figures are never available to us.

## Key files

- **`cukai_pipeline.py`** — Reads the analyst's working file at `D:\cukai kompetitor` (`REKAP RAPIH` summary sheet + per-competitor detail sheets down to package/SKU level). Read-only: nothing here writes back to that file.
- **`12_Cukai_Kompetitor.py`** — The page: displays the "Bir OT vs Musuh" recap plus per-competitor detail.

## Notes

- A region-level breakdown file (`FORMAT CUKAI WILAYAH.xlsx`) and some uncovered per-brand raw data exist in the same folder but are intentionally not yet parsed — the structure is significantly more complex (4-level headers, possible multi-block layout).
