r"""
CUKAI PIPELINE
Baca data volume kompetitor (estimasi dari data cukai/pajak minuman beralkohol
-- satu-satunya cara mengetahui volume kompetitor karena angka penjualan
mereka sendiri tidak pernah kita punya) dari file kerja analis di
D:\cukai kompetitor. TIDAK menulis apa pun ke file itu -- baca & tampilkan
saja, sama seperti pola Gabungan HOREKA.

V1 cuma cover sheet 'REKAP RAPIH' (workbook Cukai Kompetitor.xlsx) -- tabel
bulanan bersih "Bir OT vs Musuh" per brand. Folder ini juga punya file
level-wilayah (FORMAT CUKAI WILAYAH.xlsx) dan data mentah per-brand yang
BELUM di-cover di sini -- strukturnya jauh lebih kompleks (header 4 tingkat,
kemungkinan multi-blok), disengaja skip dulu sampai v1 ini dievaluasi.
"""

import datetime
from pathlib import Path

import openpyxl
import pandas as pd

CUKAI_DIR = Path(r"D:\cukai kompetitor")
REKAP_FILE = CUKAI_DIR / "Cukai Kompetitor.xlsx"
REKAP_SHEET = "REKAP RAPIH"

MONTH_ID = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGS", "SEP", "OKT", "NOV", "DES"]


def is_available() -> bool:
    return REKAP_FILE.exists()


def load_rekap_rapih() -> pd.DataFrame:
    """Parse REKAP RAPIH jadi long-format (Brand, Month, Qty, Share) -- kolom bulan
    dideteksi otomatis lewat header row 2 yang selnya bertipe datetime (bukan
    hardcode posisi kolom), supaya tahan kalau baris/kolom quarter/rata2 di
    sekitarnya berubah. Tiap kolom bulan itu QTY-nya persis di kolom itu, share
    (pangsa, 0.0-1.0) di kolom SEBELAHNYA -- pola ini konsisten dicek lewat
    merged-cell range file aslinya (mis. D2:E2 utk Jan25 = kolom D:qty, E:share)."""
    if not is_available():
        return pd.DataFrame(columns=["Brand", "Month", "MonthKey", "Qty", "Share"])

    wb = openpyxl.load_workbook(REKAP_FILE, data_only=True, read_only=True)
    ws = wb[REKAP_SHEET]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return pd.DataFrame(columns=["Brand", "Month", "MonthKey", "Qty", "Share"])

    header = rows[1]
    month_cols = [i for i, v in enumerate(header) if isinstance(v, datetime.datetime)]

    records = []
    for row in rows[2:]:
        brand = row[0]
        if not brand or str(brand).strip() == "" or str(brand).strip().lower() == "total":
            continue
        brand = str(brand).strip()
        for c in month_cols:
            month_dt = header[c]
            qty = row[c] if c < len(row) else None
            share = row[c + 1] if c + 1 < len(row) else None
            if qty is None and share is None:
                continue
            month_key = f"{MONTH_ID[month_dt.month - 1]}{month_dt.year % 100:02d}"
            records.append({
                "Brand": brand,
                "Month": month_dt.strftime("%b %y"),
                "MonthKey": month_key,
                "MonthDate": month_dt,
                "Qty": qty or 0,
                "Share": share,
            })

    return pd.DataFrame(records)


def get_last_modified() -> datetime.datetime | None:
    if not is_available():
        return None
    return datetime.datetime.fromtimestamp(REKAP_FILE.stat().st_mtime)
