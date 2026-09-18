# omset-app

The OMSHAR/EAO sales reporting app — a multi-user Streamlit app served over the office LAN, with login and per-page access levels (0–5).

## Entry points

- **`app.py`** — The real entry point (run via `CARI OUTLET.bat` / `CARI OUTLET (LAN).bat`). Builds the sidebar navigation explicitly (`st.navigation()`/`st.Page()`) and filters it by the logged-in user's access level *before* rendering, so a page a user can't access never appears in the menu at all — not just blocked after clicking. `config/config.yaml`'s `pages:` section is the source of truth for each page's required level; `PAGE_DEFS` in `app.py` must keep the exact same path strings, or a moved/renamed page silently becomes unreachable by everyone (falls back to level 99).
- **`omset_search_app.py`** — "Omset Seeker": the original outlet search + report tool, registered directly in `PAGE_DEFS` rather than living in a domain folder (it's the oldest, most central page and predates the domain split).

## App directory

Each folder below is documented in its own `README.md`:

| Folder | What it does |
|---|---|
| [`core/`](core/README.md) | Shared auth, database, paths, and the core sales query engine — used by everything else |
| [`omset_pipeline/`](omset_pipeline/README.md) | Raw OMSHAR → CSV/XLSX transpose pipeline |
| [`mclub/`](mclub/README.md) | Outlet tier classification (Gold/Platinum/MCLUB) |
| [`cukai/`](cukai/README.md) | Competitor volume estimates from excise/tax data |
| [`daily_report/`](daily_report/README.md) | Daily report folder automation |
| [`bpr/`](bpr/README.md) | NORM/STOK/DOI/Order daily rollup (BPR) |
| [`eao/`](eao/README.md) | EAO sell-out system monitoring + manual sync |
| [`sku/`](sku/README.md) | Per-SKU-variant queries: claims, manifest, sync list, big-brand detail |
| [`sync/`](sync/README.md) | Sync + transpose runner, gabungan status, cutoff checker |
| [`admin/`](admin/README.md) | Home, Dashboard, user management, audit trail |

## Config

`config/config.yaml` holds the access-level definitions and the per-page minimum level — edit it to move a page between levels without touching code.

## Folder structure history

This app used to be a flat collection of `.py` files directly under the repo root. It was reorganized into the domain folders above (one migration per domain, each verified independently before merging) and then wrapped into this `omset-app/` folder as a single unit, to make room for other projects (like `wiki-llm/`) to live alongside it in the same repository without mixing concerns.
