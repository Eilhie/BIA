# sku

Per-SKU-variant query engine and the four pages built on it. Distinct from `core/omset_seeker.py`, which reports *brand-level* rollups — this domain answers questions about one specific SKU variant (e.g. "ABIDIN CAN" alone, not total ABIDIN bottle+can).

## Key files

- **`sku_lookup.py`** — Reads raw OMSHAR files directly per SKU (reusing `transpose.py`'s `stack_sheets()` pattern) rather than through the transpose pipeline, because `transpose.py` stacks all of a brand's SKU-variant files together without keeping a source-file marker — per-SKU identity is lost by the time data reaches the normal pipeline output.
- **`3_Cek_Klaim_SKU.py`** — QTY (KRT) trend per SKU per outlet, used to verify promo claims that are calculated per specific SKU (promo/rupiah math itself stays manual, outside this tool).
- **`4_Atur_SKU_Sync.py`** — Manages `SKU_LIST` (`D:\DB OMSHAR\SKU_LIST\{UMUM,HOREKA}\*.txt`), the list of SKU codes actually pulled during Sync. Removing a code here stops it being synced, which can silently make a brand's report go stale — that risk is surfaced directly on this page.
- **`7_Detail_SKU_Brand_Besar.py`** — Per-outlet detail for the largest brands (PALS, PLAG, PPIL, PRL, WBR, SINGARAJA, SOMAEK), broken down to individual SKU variant rather than brand total. Most variants here were never touched by `transpose.py`, so the fast `SKU_RAW` cache path doesn't apply — expect ~20–25 seconds per uncached SKU, which is why only the already-fast ones are shown by default.
- **`2_SKU_Manifest.py`** — Single source of truth reconciling three layers that are easy to confuse: what `SKU_LIST` *tries* to sync, what actually landed in the synced DB, and what's *active* in `transpose.py`'s brand mapping.

## Notes

- `sku_lookup.py` is imported cross-domain by `sync/1_Sync_dan_Transpose.py` — a reminder that "domain folder" here groups by *feature*, not by a strict dependency boundary.
