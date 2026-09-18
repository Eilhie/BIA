# mclub

Automates outlet tier classification (Gold / Platinum / MCLUB) plus competitive analysis (OMS LOSS, industry volume, market share), replacing a manual process built around a 55MB/13MB working file, a recap sheet, and a PDF.

## Key files

- **`mclub_pipeline.py`** — Reads the RAW file provided by another division (~9 months of history + pre-determined tier/layer per outlet + competitor brand volume), and upserts it into a local archive that keeps every month ever seen (new months appended, the 1–2 most recent overlapping months overwritten with the latest RAW version).
- **`5_Outlet_Lapisan_MClub.py`** — The page: shows outlet tiers and competitive metrics.

## Notes

- Tier/layer values are a pass-through from the RAW file, never recomputed locally — they cannot be reconstructed from data this pipeline has ever seen (would need Jan–Jun 2025 history that was never provided).
- The archive (`mclub_pipeline/archive_umum.csv`, `archive_horeka.csv` — a data folder, not to be confused with the `mclub_pipeline.py` *file*) is real accumulated history, gitignored, and computed relative to `__file__`. If this folder ever needs to move, move the data with it.
