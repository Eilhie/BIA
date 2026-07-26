"""
DASHBOARD
Ringkasan kesehatan pipeline OMSHAR -- cutoff data, freshness sync/transpose,
kelengkapan brand, info Toko Gabungan, coverage SKU. Semua dihitung dari
fungsi yang sudah ada di omset_seeker.py / transpose.py, tanpa logika baru.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(r"D:\SDAAREA\omset_pipeline")))
import transpose as t  # noqa: E402

from omset_seeker import find_latest_toko_gabungan, get_cutoff_date, load_gabungan_map  # noqa: E402

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

DB_DIR = Path(r"D:\DB OMSHAR\DB")
TRANSPOSED_DIR = Path(r"D:\SDAAREA\omset_pipeline\output\DB TRANSPOSED")
SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")


def newest_mtime(paths) -> datetime | None:
    times = [p.stat().st_mtime for p in paths if p.exists()]
    return datetime.fromtimestamp(max(times)) if times else None


def fmt_age(dt: datetime | None) -> str:
    if dt is None:
        return "tidak ada file"
    days = (datetime.now() - dt).days
    if days == 0:
        return f"{dt:%d %b %H:%M} (hari ini)"
    return f"{dt:%d %b %H:%M} ({days} hari lalu)"


# ── 1. Cutoff data ──────────────────────────────────────────────────────────
st.subheader("Cutoff Data")
c1, c2 = st.columns(2)
c1.metric("UMUM", get_cutoff_date(omshar_type="UMUM") or "-")
c2.metric("HOREKA", get_cutoff_date(omshar_type="HOREKA") or "-")

st.divider()

# ── 2. Freshness sumber data & hasil transpose ──────────────────────────────
st.subheader("Freshness")
f1, f2 = st.columns(2)
with f1:
    st.markdown(f"**Sumber (`{DB_DIR}`)**")
    umum_src = newest_mtime(DB_DIR.glob("OMSHAR UMUM *.xls"))
    horeka_src = newest_mtime(DB_DIR.glob("OMSHAR HOREKA *.xls"))
    st.write(f"UMUM: {fmt_age(umum_src)}")
    st.write(f"HOREKA: {fmt_age(horeka_src)}")
with f2:
    st.markdown("**Hasil transpose (`omset_pipeline\\output`)**")
    umum_out = newest_mtime((TRANSPOSED_DIR / "UMUM").glob("*.xlsx"))
    horeka_out = newest_mtime((TRANSPOSED_DIR / "HOREKA").glob("*.xlsx"))
    st.write(f"UMUM: {fmt_age(umum_out)}")
    st.write(f"HOREKA: {fmt_age(horeka_out)}")

if umum_src and umum_out and umum_src > umum_out:
    st.warning("Sumber UMUM lebih baru dari hasil transpose terakhir -- mungkin perlu transpose ulang.")
if horeka_src and horeka_out and horeka_src > horeka_out:
    st.warning("Sumber HOREKA lebih baru dari hasil transpose terakhir -- mungkin perlu transpose ulang.")

st.divider()

# ── 3. Kelengkapan brand hasil transpose ────────────────────────────────────
st.subheader("Kelengkapan Brand (Hasil Transpose)")


def check_brands(brand_list, out_dir: Path, omshar_type: str):
    existing = {p.stem.replace(f"OMSHAR {omshar_type} ", "").replace(" TRANSPOSED", "") for p in out_dir.glob("*.xlsx")}
    missing = [b for b in brand_list if b not in existing]
    return len(brand_list) - len(missing), len(brand_list), missing


umum_ok, umum_total, umum_missing = check_brands(t.BRAND_ORDER, TRANSPOSED_DIR / "UMUM", "UMUM")
horeka_brands = t.BRAND_ORDER + t.HOREKA_KEG_BRAND_ORDER
horeka_ok, horeka_total, horeka_missing = check_brands(horeka_brands, TRANSPOSED_DIR / "HOREKA", "HOREKA")

b1, b2 = st.columns(2)
b1.metric("UMUM", f"{umum_ok}/{umum_total} brand")
b2.metric("HOREKA (termasuk 7 KEG)", f"{horeka_ok}/{horeka_total} brand")

if umum_missing:
    st.warning(f"UMUM belum ditranspose: {', '.join(umum_missing)}")
if horeka_missing:
    st.warning(f"HOREKA belum ditranspose: {', '.join(horeka_missing)}")

st.divider()

# ── 4. Toko Gabungan ─────────────────────────────────────────────────────────
gab_title_col, gab_btn_col = st.columns([5, 1])
gab_title_col.subheader("Toko Gabungan")
if gab_btn_col.button("Refresh"):
    # load_gabungan_map() cuma ke-clear otomatis lewat halaman Transpose (lihat
    # pages/1_Sync_dan_Transpose.py) -- kalau file Toko Gabungan bulanan diganti
    # TANPA jalanin transpose (file terpisah, update manual, tidak selalu bareng
    # siklus sync OMSHAR), tidak ada yang trigger refresh. Tombol ini jalan pintasnya.
    load_gabungan_map.cache_clear()
    st.rerun()

gab_path = find_latest_toko_gabungan()
if gab_path is None:
    st.warning("File Toko Gabungan tidak ditemukan.")
else:
    gab_map = load_gabungan_map()
    g1, g2 = st.columns(2)
    g1.metric("File aktif", gab_path.name)
    g2.metric("Jumlah grup gabungan", len(gab_map))

st.divider()

# ── 5. Coverage SKU (dipetakan ke brand vs tidak) ───────────────────────────
st.subheader("Coverage SKU")


def sku_coverage(list_dir: Path, file_map: dict, extra_map: dict | None = None):
    mapped_files = set()
    for files in file_map.values():
        mapped_files.update(files)
    if extra_map:
        for files in extra_map.values():
            mapped_files.update(files)

    total = 0
    mapped = 0
    for txt in list_dir.glob("*.txt"):
        skus = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        total += len(skus)
        mapped += sum(1 for s in skus if s in mapped_files)
    return mapped, total


umum_mapped, umum_sku_total = sku_coverage(SKU_LIST_DIR / "UMUM", t.UMUM_FILE)
horeka_mapped, horeka_sku_total = sku_coverage(SKU_LIST_DIR / "HOREKA", t.HOREKA_FILE, t.HOREKA_KEG_FILE)

s1, s2 = st.columns(2)
s1.metric("UMUM", f"{umum_mapped}/{umum_sku_total} SKU terpetakan")
s2.metric("HOREKA", f"{horeka_mapped}/{horeka_sku_total} SKU terpetakan")
st.caption(
    "SKU yang disync dari server tapi belum masuk brand manapun -- lihat SKU Manifest "
    "untuk daftar lengkapnya per kategori."
)
