# admin

Cross-cutting pages that don't belong to any single data domain.

## Key files

- **`15_Home.py`** — Landing page (replacing Omset Seeker as the default). Shows gamified "Player Progress" (level/XP computed from the *existing* access log — no new instrumentation added) plus quick-links to common pages.
- **`0_Dashboard.py`** — Pipeline health overview: data cutoff, sync/transpose freshness, brand completeness, Toko Gabungan info, SKU coverage — entirely computed from functions that already exist elsewhere (`core/omset_seeker.py`, `omset_pipeline/transpose.py`), no new logic.
- **`8_Kelola_User.py`** — Admin-only (level 5): create/edit accounts, set access level (0–5), activate/deactivate, reset passwords.
- **`9_Audit_Trail.py`** — Admin-only: access log and login-attempt history, split out from Kelola User so you can trace one person's activity without scrolling past account-management forms.

## Notes

- "Level" means two different things in this app on purpose: the RBAC access level (0–5, set in Kelola User) and the gamification level shown on Home (computed from XP). `auth.py`'s user-bar no longer shows the RBAC number in the common header — only a role label (e.g. "Admin") — specifically so "Level" reads unambiguously as the gamification concept everywhere a user actually sees it.
