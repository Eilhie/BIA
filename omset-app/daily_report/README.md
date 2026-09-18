# daily_report

Automates a daily routine that used to be manual and inconsistent: copying every file from the Daily Report root folder into today's dated subfolder.

## Key files

- **`daily_report_setup.py`** — The actual logic (no Streamlit dependency), so it can be reused both by the dedicated page and by a notification modal shown to Admins on every page in `app.py`, without duplicating the copy logic.
- **`16_Setup_Daily_Report.py`** — The page: runs the setup automatically when opened (idempotent — never overwrites or deletes files already copied), same pattern as the BPR page's local backup step.

## Why this exists

A real audit of one month found only 7 of 13 working days had exactly the expected 25 files — 2 days missed entirely, several days short or with extra files, and one real filename typo. Manual copying was genuinely unreliable, not a hypothetical problem.
