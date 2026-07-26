"""
SKU LOOKUP
Query trend KRT (Jan-Des 2026) per VARIAN SKU individu (bukan gabungan per brand
seperti omset_seeker.py) -- dipakai buat cek klaim yang dihitung dari QTY per SKU
spesifik (mis. "ABIDIN CAN" saja, bukan total ABIDIN botol+kaleng).

transpose.py men-stack semua file varian SKU satu brand jadi satu tanpa kolom
penanda file sumber (lihat process_brand()), jadi identitas per-SKU sudah hilang
begitu masuk pipeline transpose. Modul ini baca LANGSUNG dari file OMSHAR mentah
per SKU (reuse pola stack_sheets() dari transpose.py), di luar pipeline transpose,
supaya tidak perlu ubah format output yang sudah dipakai omset_seeker.py.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd
import xlrd

from omset_pipeline.transpose import (
    DAPUL, LAPUL, HOREKA, HEADER_ROWS, COL_SITE, CSV_DIR,
    UMUM_FILE, HOREKA_FILE, HOREKA_KEG_FILE, stack_sheets,
)
from omset_seeker import resolve_site_list

# Sumber data sinkron dari server -- lihat feedback_data_source_location:
# D:\SDAAREA\DB (default nominal transpose.py) kosong, data asli ada di sini.
OMSHAR_DIR = Path(r"D:\DB OMSHAR\DB")

WILAYAH_ORDER = {"UMUM": DAPUL + LAPUL, "HOREKA": HOREKA}

# Kolom KRT 2026 saja (0-indexed, xlrd) -- lihat project-omshar-technical:
# 2025=140-151, 2026=152-163.
COLS_2026 = list(range(152, 164))
MONTH_LABELS_2026 = [
    f"{m} 2026"
    for m in ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGS", "SEP", "OKT", "NOV", "DES"]
]

_EMPTY_TREND = {m: 0 for m in MONTH_LABELS_2026}


def get_sku_catalog(category: str) -> dict[str, list[str]]:
    """Brand -> daftar nama file SKU individu, dari mapping brand->file yang sudah
    diverifikasi lewat pembongkaran formula VLOOKUP asli (UMUM_FILE/HOREKA_FILE di
    transpose.py) -- bukan dari SKU_LIST (itu cuma daftar buat sync robocopy, tidak
    selalu 1:1 dengan brand di pipeline, mis. tidak ada entri SPA/PRL terpisah)."""
    file_map = UMUM_FILE if category == "UMUM" else HOREKA_FILE
    catalog = {brand: list(files) for brand, files in file_map.items()}
    if category == "HOREKA":
        for brand, files in HOREKA_KEG_FILE.items():
            catalog[f"{brand} (KEG)"] = list(files)
    return catalog


def _sku_raw_cache_path(category: str, sku_name: str) -> Path:
    return CSV_DIR / category / "SKU_RAW" / f"{sku_name}.csv"


@lru_cache(maxsize=None)
def load_sku_raw(category: str, sku_name: str) -> pd.DataFrame:
    """Site + KRT 2026 untuk satu varian SKU individu.

    Jalur cepat: baca CSV ringan yang sudah disiapkan transpose.py lewat
    write_sku_raw_csv() -- numpang di parsing yang SUDAH dilakukan pipeline transpose,
    jadi baca-nya milidetik, bukan ~20 detik/file. Fallback ke baca .xls mentah
    langsung kalau CSV itu belum ada (mis. SKU baru yang belum pernah ditranspose
    sejak fitur ini ada, atau setelah Sync tapi sebelum Transpose jalan)."""
    cached = _sku_raw_cache_path(category, sku_name)
    if cached.exists():
        out = pd.read_csv(cached, dtype={"Site": str}, encoding="utf-8-sig")
        out["Site"] = out["Site"].str.strip()
        for m in MONTH_LABELS_2026:
            out[m] = pd.to_numeric(out[m], errors="coerce").fillna(0)
        return out

    src = OMSHAR_DIR / f"OMSHAR {category} {sku_name}.xls"
    if not src.exists():
        return pd.DataFrame(columns=["Site"] + MONTH_LABELS_2026)

    wb = xlrd.open_workbook(str(src), on_demand=True)
    try:
        _, rows = stack_sheets(wb, WILAYAH_ORDER[category])
    finally:
        wb.release_resources()

    if not rows:
        return pd.DataFrame(columns=["Site"] + MONTH_LABELS_2026)

    df = pd.DataFrame(rows)
    out = df[[COL_SITE] + COLS_2026].copy()
    out.columns = ["Site"] + MONTH_LABELS_2026
    out["Site"] = out["Site"].astype(str).str.strip()
    for m in MONTH_LABELS_2026:
        out[m] = pd.to_numeric(out[m], errors="coerce").fillna(0)
    return out


def get_sku_trend(category: str, sku_name: str, site: str) -> dict:
    """KRT per bulan (Jan-Des 2026) untuk satu varian SKU + satu outlet. Gabungan-aware
    lewat resolve_site_list() -- kalau site kode toko gabungan, dijumlah dari anaknya."""
    site_list = resolve_site_list(site)
    df = load_sku_raw(category, sku_name)
    match = df[df["Site"].isin(site_list)]
    if match.empty:
        return dict(_EMPTY_TREND)
    return match[MONTH_LABELS_2026].sum().to_dict()
