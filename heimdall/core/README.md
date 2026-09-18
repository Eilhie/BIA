# core

Shared infrastructure used by every other app in `heimdall/`. Nothing here is domain-specific — if a change would only make sense for one brand/workflow, it belongs in that domain's own folder instead.

## Key files

- **`auth.py`** — Login, session cookies, password hashing, and per-page access levels (0–5). Levels are defined in `config/config.yaml`, not hardcoded here, so access can be adjusted without touching code. `require_level(n, page=...)` is called at the top of every page as a second layer of protection, in addition to `app.py` filtering the sidebar menu before it renders.
- **`database.py`** — SQLite connection handling plus the access-log/audit-trail schema. `DB_PATH` is computed from `__file__` (not the process's working directory) — this matters: a bare relative path here previously broke silently when the app's launch directory changed, making the whole user database appear empty.
- **`paths.py`** — The single source of truth for every external (outside the repo) data path: `D:\DB OMSHAR\...`, `D:\EAO`, Google Drive BPR folder, etc. Every path is overridable via an environment variable (`SDA_*`), with the current PC's real path as the default — this is what lets the app run on a different machine without code changes.
- **`omset_seeker.py`** — The core sales query engine: loads transposed brand CSVs, resolves outlet/site lookups, computes cutoff dates, and (optionally) accelerates queries via a SQLite cache. Used across almost every domain, not just the Omset Seeker page itself.
- **`render_outlet_image.py`** — Renders the per-outlet OMSET report as an HTML table / PNG image, matching the original Excel layout pixel-for-pixel.

## A lesson worth keeping in mind

Both `auth.py`'s `CONFIG_PATH` and `database.py`'s `DB_PATH` compute their target file location. Always anchor that kind of path to `Path(__file__).resolve().parent...`, never to a bare relative string — a bare relative path silently resolves against whatever the *process's* working directory happens to be, which is not guaranteed to match where the file itself lives.
