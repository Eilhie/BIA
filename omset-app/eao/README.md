# eao

Monitoring and manual-sync visibility for EAO — a sell-out data system entirely separate from OMSHAR.

## Key files

- **`eao_pipeline.py`** — Reads from `D:\EAO`, which Windows Task Scheduler + `sync_eao.bat` (robocopy) already syncs automatically from `\\10.4.1.25\Bev\EAO` every ~10 minutes, independent of this app. This module never shells out to or modifies `sync_eao.bat` — it only mirrors the same file-selection logic natively in Python (needed because the `.bat` has a `pause` + GUI popup that would hang if invoked headlessly from Streamlit).
- **`11_EAO_Sync.py`** — The page: shows what's on the server (including files the scheduled task hasn't pulled yet), what's local, sync history, and a manual sync button for when you can't wait for the schedule.

## Notes

- `TOTAL DIVISI` sheet carries the real DPB/DPT/SUM/KAL/SUL/NKS regional hierarchy — see project memory for details if extending this.
