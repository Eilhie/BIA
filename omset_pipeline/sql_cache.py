"""
SQL CACHE — v4 prototype (Blueprint §7)
Standalone, NOT wired into omset_seeker.py, sku_lookup.py, or any Streamlit page.
Builds a per-channel SQLite file (UMUM.db / HOREKA.db) at the SKU grain, serving
both Omset Seeker (brand rollups, is_rollup=1) and Detail SKU Brand Besar
(per-variant browse, all rows) from one shared fact table.

Schema: dim_outlet, dim_brand, dim_sku, fact_krt (site_id, sku_id, month, krt).
See the "Omset SQL Blueprint" artifact for the full design + rationale.

THIS FILE IS A PROTOTYPE. Nothing here is called by the live app yet.
"""

import csv
import os
import sqlite3
import time
import uuid
from pathlib import Path

import xlrd

import transpose as t

DEST_DB = Path(os.environ.get("OMSHAR_DIR", str(Path(__file__).resolve().parent.parent / "DB")))
OUT_DIR = Path(__file__).resolve().parent / "output" / "SQL_CACHE"

# Columns needed for the lightweight (Pass B) reader -- Site/Outlet/address for
# dim_outlet, plus the 24 KRT month columns. NOT `range(ncols)` like
# transpose.stack_sheets() -- that's the whole optimization (see Blueprint §7,
# "Stop reading columns nobody asked for").
COL_WIL, COL_SITE, COL_CUST = 0, 1, 2
COL_PROPINSI, COL_KOTA, COL_KECAMATAN, COL_ALAMAT = 11, 12, 13, 18
COLS_2025 = list(range(140, 152))
COLS_2026 = list(range(152, 164))
NEEDED_COLS = [COL_WIL, COL_SITE, COL_CUST, COL_PROPINSI, COL_KOTA, COL_KECAMATAN, COL_ALAMAT] + COLS_2025 + COLS_2026

MONTHS_2025 = [f"2025{m:02d}" for m in range(1, 13)]
MONTHS_2026 = [f"2026{m:02d}" for m in range(1, 13)]
MONTH_KEYS = MONTHS_2025 + MONTHS_2026  # parallel to COLS_2025 + COLS_2026


def _row_dict(sh, r, cols):
    """Read ONLY `cols` from row `r` -- the whole point vs stack_sheets()'s full-row read."""
    return {c: sh.cell_value(r, c) for c in cols}


def read_sku_pruned(omshar_type: str, sku_code: str, sheet_order: list[str]) -> list[dict]:
    """Lightweight per-SKU reader (Pass B) -- Site/address + 24 KRT columns only,
    NOT every column like transpose.stack_sheets(). Mirrors stack_sheets()'s
    DAPUL/LAPUL region-stacking (no header/periode logic needed here -- this
    feeds fact_krt directly, not a CSV with a header block)."""
    path = DEST_DB / f"OMSHAR {omshar_type} {sku_code}.xls"
    if not path.exists():
        return []
    wb = xlrd.open_workbook(str(path), on_demand=True)
    out = []
    available = set(wb.sheet_names())
    for name in sheet_order:
        if name not in available:
            continue
        sh = wb.sheet_by_name(name)
        if sh.nrows <= t.HEADER_ROWS:
            continue
        for r in range(t.HEADER_ROWS, sh.nrows):
            row = _row_dict(sh, r, NEEDED_COLS)
            site = str(row[COL_SITE]).strip()
            if not site:
                continue
            out.append(row)
    wb.release_resources()
    return out


def time_pruned_read(omshar_type: str, sku_code: str, sheet_order: list[str]) -> tuple[float, int]:
    t0 = time.time()
    rows = read_sku_pruned(omshar_type, sku_code, sheet_order)
    return time.time() - t0, len(rows)


# ── UNIFIED PASS: Pass A and Pass B collapse into one mechanism ──────────────
# Realization while building this: read_sku_pruned() being ~12x faster than
# stack_sheets() means Pass A doesn't need to melt the already-written brand
# CSVs at all -- it can read raw .xls directly, same as Pass B, just with
# is_rollup=1 instead of 0. transpose.py's own UMUM_FILE/HOREKA_FILE already
# treats a multi-file brand (e.g. SIMER's 2 files) as independent per-site
# ROWS stacked together, not merged/summed by site -- aggregation happens at
# query time (see stack_sheets() docstring: "agregasi per site dilakukan di
# omset_seeker saat query"). SUM(krt) GROUP BY brand in SQL replicates that
# exact behavior, so the "rollup" files need no different treatment from the
# "extra variant" files -- same reader, same shape, only the is_rollup tag
# and the source file-list differ. Two mechanisms collapsed into one.

def schema_ddl() -> list[str]:
    return [
        """CREATE TABLE dim_outlet (
            site_id     INTEGER PRIMARY KEY,
            site        TEXT UNIQUE NOT NULL,
            wilayah     TEXT,
            outlet      TEXT,
            propinsi    TEXT,
            kota        TEXT,
            kecamatan   TEXT,
            alamat      TEXT
        )""",
        """CREATE TABLE dim_brand (
            brand_id     INTEGER PRIMARY KEY,
            omshar_type  TEXT NOT NULL,
            brand        TEXT NOT NULL,
            UNIQUE(omshar_type, brand)
        )""",
        """CREATE TABLE dim_sku (
            sku_id       INTEGER PRIMARY KEY,
            omshar_type  TEXT NOT NULL,
            sku_code     TEXT NOT NULL,
            brand_id     INTEGER NOT NULL REFERENCES dim_brand(brand_id),
            is_rollup    INTEGER NOT NULL,
            UNIQUE(omshar_type, sku_code)
        )""",
        """CREATE TABLE fact_krt (
            site_id  INTEGER NOT NULL REFERENCES dim_outlet(site_id),
            sku_id   INTEGER NOT NULL REFERENCES dim_sku(sku_id),
            month    INTEGER NOT NULL,
            krt      REAL NOT NULL,
            PRIMARY KEY (site_id, sku_id, month)
        ) WITHOUT ROWID""",
        "CREATE INDEX idx_fact_sku ON fact_krt(sku_id, site_id)",
        """CREATE TABLE meta (
            key    TEXT PRIMARY KEY,
            value  TEXT
        )""",
    ]


def build_sku_plan(omshar_type: str, extra_groups: list[str]) -> dict:
    """(sku_code -> (brand, is_rollup)) for one channel -- rollup members from
    transpose.py's own file_map (ground truth, already verified against the
    real Excel template), extras from the given SKU_LIST groups minus
    whatever's already a rollup member (so a code is never counted twice)."""
    file_map = t.UMUM_FILE if omshar_type == "UMUM" else t.HOREKA_FILE
    extra_map = t.HOREKA_KEG_FILE if omshar_type == "HOREKA" else None

    plan = {}
    for brand, files in file_map.items():
        for f in files:
            plan[f] = (brand, 1)
    if extra_map:
        for brand, files in extra_map.items():
            for f in files:
                plan[f] = (brand, 1)

    sku_list_dir = Path(r"D:\DB OMSHAR\SKU_LIST") / omshar_type
    for group in extra_groups:
        txt = sku_list_dir / f"{group}.txt"
        if not txt.exists():
            continue
        codes = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        for code in codes:
            if code not in plan and (DEST_DB / f"OMSHAR {omshar_type} {code}.xls").exists():
                plan[code] = (group, 0)  # display-only grouping, see Blueprint §7
    return plan


def build_channel_db(omshar_type: str, sku_plan: dict, out_path: Path) -> dict:
    """Build one channel's SQLite file from a {sku_code: (brand, is_rollup)}
    plan. Writes to a .tmp file and atomically swaps it in -- same pattern as
    every other write in this codebase (see transpose._atomic_write)."""
    sheet_order = t.DAPUL + t.LAPUL if omshar_type == "UMUM" else t.HOREKA
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f".{out_path.name}.{uuid.uuid4().hex}.tmp")

    con = sqlite3.connect(tmp_path)
    try:
        for ddl in schema_ddl():
            con.execute(ddl)

        brand_ids: dict[str, int] = {}
        outlet_ids: dict[str, int] = {}
        stats = {"skus": 0, "outlets": 0, "fact_rows": 0, "read_seconds": 0.0}

        for sku_code, (brand, is_rollup) in sku_plan.items():
            if brand not in brand_ids:
                cur = con.execute(
                    "INSERT INTO dim_brand (omshar_type, brand) VALUES (?, ?)",
                    (omshar_type, brand),
                )
                brand_ids[brand] = cur.lastrowid
            brand_id = brand_ids[brand]

            t0 = time.time()
            rows = read_sku_pruned(omshar_type, sku_code, sheet_order)
            stats["read_seconds"] += time.time() - t0
            if not rows:
                continue

            cur = con.execute(
                "INSERT INTO dim_sku (omshar_type, sku_code, brand_id, is_rollup) VALUES (?, ?, ?, ?)",
                (omshar_type, sku_code, brand_id, is_rollup),
            )
            sku_id = cur.lastrowid
            stats["skus"] += 1

            fact_batch = []
            for row in rows:
                site = str(row[COL_SITE]).strip()
                if site not in outlet_ids:
                    cur2 = con.execute(
                        "INSERT INTO dim_outlet (site, wilayah, outlet, propinsi, kota, kecamatan, alamat) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (site, row[COL_WIL], row[COL_CUST], row[COL_PROPINSI],
                         row[COL_KOTA], row[COL_KECAMATAN], row[COL_ALAMAT]),
                    )
                    outlet_ids[site] = cur2.lastrowid
                    stats["outlets"] += 1
                site_id = outlet_ids[site]

                for c, month_key in zip(COLS_2025 + COLS_2026, MONTH_KEYS):
                    v = row[c]
                    if isinstance(v, (int, float)) and v != 0:
                        fact_batch.append((site_id, sku_id, int(month_key), float(v)))

            con.executemany(
                "INSERT OR REPLACE INTO fact_krt (site_id, sku_id, month, krt) VALUES (?, ?, ?, ?)",
                fact_batch,
            )
            stats["fact_rows"] += len(fact_batch)

        con.execute("INSERT INTO meta VALUES ('built_at', ?)", (str(time.time()),))
        con.execute("INSERT INTO meta VALUES ('sku_count', ?)", (str(stats["skus"]),))
        con.execute("INSERT INTO meta VALUES ('fact_row_count', ?)", (str(stats["fact_rows"]),))
        con.commit()
    finally:
        con.close()

    os.replace(tmp_path, out_path)
    return stats


# ── incremental refresh (Blueprint §7 "kill build cost") ─────────────────────
# The full rebuild above is safe by construction -- it starts from an EMPTY
# .tmp file, so every row present is exactly what this run read, nothing can
# go stale. Incremental refresh is different: it starts from the EXISTING
# .db and only re-reads SKUs whose source .xls changed (mtime-based, same
# pattern as robocopy /XO and load_brand()'s Parquet check elsewhere in this
# codebase). That means old rows for an unchanged SKU stay untouched -- fine.
# But for a SKU that DID change, `INSERT OR REPLACE` alone is not enough: a
# month that goes from nonzero to zero on a later cutoff is never inserted
# (zero values are skipped -- see build_channel_db), so its OLD nonzero row
# would silently survive forever if we only ever inserted. The fix: DELETE
# every existing fact_krt row for that sku_id FIRST, then insert the fresh
# read -- turns "cutoff advanced from 10 Sep to 30 Sep" into a clean resync
# instead of a slow accumulation of stale numbers.

def refresh_sku(con: sqlite3.Connection, omshar_type: str, sku_code: str,
                 brand: str, is_rollup: int, sheet_order: list[str]) -> int:
    """Re-sync ONE sku's fact rows against its current raw file. Safe to call
    on a sku that's never been seen (creates dim_brand/dim_sku rows) or one
    that already has data (deletes it first). Returns rows written."""
    cur = con.execute(
        "INSERT OR IGNORE INTO dim_brand (omshar_type, brand) VALUES (?, ?)",
        (omshar_type, brand),
    )
    brand_id = con.execute(
        "SELECT brand_id FROM dim_brand WHERE omshar_type=? AND brand=?",
        (omshar_type, brand),
    ).fetchone()[0]

    cur = con.execute(
        "INSERT INTO dim_sku (omshar_type, sku_code, brand_id, is_rollup) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(omshar_type, sku_code) DO UPDATE SET brand_id=excluded.brand_id, is_rollup=excluded.is_rollup",
        (omshar_type, sku_code, brand_id, is_rollup),
    )
    sku_id = con.execute(
        "SELECT sku_id FROM dim_sku WHERE omshar_type=? AND sku_code=?",
        (omshar_type, sku_code),
    ).fetchone()[0]

    # THE FIX: clear this sku's old rows before writing fresh ones, so a
    # value that disappeared in the new cutoff actually disappears here too.
    con.execute("DELETE FROM fact_krt WHERE sku_id = ?", (sku_id,))

    rows = read_sku_pruned(omshar_type, sku_code, sheet_order)
    fact_batch = []
    for row in rows:
        site = str(row[COL_SITE]).strip()
        site_id = con.execute("SELECT site_id FROM dim_outlet WHERE site=?", (site,)).fetchone()
        if site_id is None:
            cur2 = con.execute(
                "INSERT INTO dim_outlet (site, wilayah, outlet, propinsi, kota, kecamatan, alamat) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (site, row[COL_WIL], row[COL_CUST], row[COL_PROPINSI],
                 row[COL_KOTA], row[COL_KECAMATAN], row[COL_ALAMAT]),
            )
            site_id = cur2.lastrowid
        else:
            site_id = site_id[0]
        for c, month_key in zip(COLS_2025 + COLS_2026, MONTH_KEYS):
            v = row[c]
            if isinstance(v, (int, float)) and v != 0:
                fact_batch.append((site_id, sku_id, int(month_key), float(v)))

    con.executemany(
        "INSERT INTO fact_krt (site_id, sku_id, month, krt) VALUES (?, ?, ?, ?)",
        fact_batch,
    )
    con.commit()
    return len(fact_batch)


# ── query shapes (prototype -- not what omset_seeker.py will call yet) ───────

def query_brand_total(db_path: Path, site: str, brand: str) -> list[tuple]:
    """Omset Seeker shape: summed, rollup members only."""
    con = sqlite3.connect(db_path)
    try:
        return con.execute(
            """SELECT f.month, SUM(f.krt) FROM fact_krt f
               JOIN dim_sku s ON s.sku_id = f.sku_id
               JOIN dim_brand b ON b.brand_id = s.brand_id
               JOIN dim_outlet o ON o.site_id = f.site_id
               WHERE o.site = ? AND b.brand = ? AND s.is_rollup = 1
               GROUP BY f.month ORDER BY f.month""",
            (site, brand),
        ).fetchall()
    finally:
        con.close()


def query_sku_breakdown(db_path: Path, site: str, brand: str) -> list[tuple]:
    """Detail SKU Brand Besar shape: every variant, unaggregated."""
    con = sqlite3.connect(db_path)
    try:
        return con.execute(
            """SELECT s.sku_code, s.is_rollup, f.month, f.krt FROM fact_krt f
               JOIN dim_sku s ON s.sku_id = f.sku_id
               JOIN dim_brand b ON b.brand_id = s.brand_id
               JOIN dim_outlet o ON o.site_id = f.site_id
               WHERE o.site = ? AND b.brand = ?
               ORDER BY s.sku_code, f.month""",
            (site, brand),
        ).fetchall()
    finally:
        con.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "_bench":
        # Quick apples-to-apples timing check against the 231.4s full-read
        # baseline measured earlier for the same file (ABIDIN, UMUM, DAPUL+LAPUL).
        elapsed, n = time_pruned_read("UMUM", "ABIDIN", t.DAPUL + t.LAPUL)
        print(f"pruned read: {elapsed:.1f}s, {n} rows")

    elif len(sys.argv) > 1 and sys.argv[1] == "_refresh_test":
        # Proves the DELETE-then-INSERT fix: build a sku with a "10 Sep
        # cutoff"-style row (AGS 2026 = 40.0), then refresh it with a "30 Sep
        # update"-style row where that same month has been revised DOWN TO
        # ZERO. Without the fix, the old 40.0 row survives forever since
        # zero values are never inserted. With it, the row is gone.
        import unittest.mock as mock

        out_path = OUT_DIR / "UMUM_refreshtest.db"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.unlink(missing_ok=True)
        con = sqlite3.connect(out_path)
        for ddl in schema_ddl():
            con.execute(ddl)

        fake_row_v1 = {COL_WIL: "TEST-WIL", COL_SITE: "9999-TESTSITE", COL_CUST: "TEST OUTLET",
                        COL_PROPINSI: "P", COL_KOTA: "K", COL_KECAMATAN: "KC", COL_ALAMAT: "A"}
        fake_row_v1.update({c: 0.0 for c in COLS_2025 + COLS_2026})
        fake_row_v1[159] = 40.0  # AGS 2026 -- "10 Sep cutoff" snapshot: 40.0

        with mock.patch("__main__.read_sku_pruned", return_value=[fake_row_v1]):
            n1 = refresh_sku(con, "UMUM", "TESTSKU", "TEST BRAND", 1, t.DAPUL)
        before = con.execute(
            "SELECT month, krt FROM fact_krt f JOIN dim_sku s ON s.sku_id=f.sku_id WHERE s.sku_code='TESTSKU'"
        ).fetchall()
        print(f"after 1st build (10 Sep cutoff): {n1} rows -> {before}")

        fake_row_v2 = dict(fake_row_v1)
        fake_row_v2[159] = 0.0  # AGS 2026 revised DOWN TO ZERO on the 30 Sep update
        fake_row_v2[160] = 12.0  # and SEP 2026 now has a real value it didn't before

        with mock.patch("__main__.read_sku_pruned", return_value=[fake_row_v2]):
            n2 = refresh_sku(con, "UMUM", "TESTSKU", "TEST BRAND", 1, t.DAPUL)
        after = con.execute(
            "SELECT month, krt FROM fact_krt f JOIN dim_sku s ON s.sku_id=f.sku_id WHERE s.sku_code='TESTSKU'"
        ).fetchall()
        print(f"after 2nd build (30 Sep cutoff): {n2} rows -> {after}")

        stale = [r for r in after if r[0] == 202608]
        new = [r for r in after if r[0] == 202609]
        assert not stale, f"BUG: stale AGS 2026 row survived: {stale}"
        assert new == [(202609, 12.0)], f"BUG: new SEP 2026 row wrong: {new}"
        print("PASS: stale zero-revision correctly deleted, new value correctly present.")
        con.close()

    elif len(sys.argv) > 1 and sys.argv[1] == "_smoketest":
        # Small end-to-end slice: PRL LAGER's real rollup members + a couple
        # of real PROST RAJAWALI-family extras -- proves the whole mechanism
        # (schema, build, atomic swap, both query shapes) against known-real
        # numbers from earlier this session, not the full 175-file scope.
        plan = {
            "RPKC320L": ("PRL LAGER", 1),
            "RPKC500L": ("PRL LAGER", 1),
            "RPKB620L": ("PRL LAGER", 1),
            "RPKB330L": ("PRL LAGER", 1),
            "PROST RAJAWALI": ("PROST RAJAWALI", 1),
        }
        out_path = OUT_DIR / "UMUM_smoketest.db"
        t0 = time.time()
        stats = build_channel_db("UMUM", plan, out_path)
        print(f"build: {time.time()-t0:.1f}s, {stats}")

        site = "7711-75012290"
        print(f"\nOmset Seeker query -- PRL LAGER @ {site}:")
        for month, krt in query_brand_total(out_path, site, "PRL LAGER"):
            print(f"  {month}: {krt}")

        print(f"\nDetail SKU query -- PRL LAGER @ {site}:")
        for sku_code, is_rollup, month, krt in query_sku_breakdown(out_path, site, "PRL LAGER"):
            print(f"  {sku_code} (rollup={is_rollup}) {month}: {krt}")
