"""
BPR PIPELINE
Replikasi Python dari template Excel "BPR BIA DAILY TEMPLATE.xlsx" (sheet
"Rekap Per DEPO" + "Rekap Per WILAYAH"), yang selama ini dihitung manual lewat
SUMIFS/AVERAGEIFS ke file raw BPR_BIA-<timestamp>.xls (sheet "BPR DETAIL") +
external link Excel yang di-relink manual tiap pagi.

Semua rumus di bawah diverifikasi PERSIS terhadap cached value template asli
tanggal 24 Aug 2026 (lihat test_bpr_pipeline.py) -- bukan tebakan:
  - NORM/STOK/DOI/ACTUAL ORDER: cuma baris dengan Proposed Order > 0 yang
    dihitung (match SUMIFS/AVERAGEIFS kriteria ">0" di template).
  - Kolom brand (Proposed Order per brand): TIDAK difilter Proposed Order > 0
    (template SUMIFS brand tidak punya kriteria itu) -- cuma match Group Item
    + Wilayah + Depo.
  - Wilayah axis Rekap Per WILAYAH BUKAN semua wilayah di raw data, tapi
    daftar tetap 6 region (DKI/Banten/Bodebek/Jatim Utara/Jatim Selatan/Bali)
    x (UMUM, HOREKA) + baris subtotal "{REGION} TOTAL" -- sama seperti
    template, karena itu cakupan area yang direkap orang yang buat template
    ini (bukan seluruh wilayah perusahaan).
  - DOI di level Wilayah dihitung ULANG langsung dari raw data (AVERAGEIFS
    per Wilayah), BUKAN rata-rata dari DOI per-Depo -- baris subtotal region
    TOTAL malah tidak punya DOI sama sekali (kosong di template asli).
"""

import re
from pathlib import Path

import pandas as pd
import xlrd

RAW_SHEET = "BPR DETAIL"

# File raw harian diarsip di sini, satu file per hari, nama-nya bawa timestamp
# lengkap -- INI yang dipakai buat cari "yang terbaru", BUKAN file di root
# "D:\Data BIA\2026\Daily Report\BPR_BIA-DAILY.xls" (kelihatan seperti master/
# current copy, tapi terbukti nyata mtime-nya macet di 4 Mei 2026 sementara
# arsip per-tanggal SELALU update -- jangan pernah baca dari root file itu).
DAILY_REPORT_DIR = Path(r"D:\Data BIA\2026\Daily Report")
KIRIM_DIR = DAILY_REPORT_DIR / "Kirim"
_RAW_NAME_RE = re.compile(r"^BPR_BIA-(\d{14})\.xls$")


def find_latest_raw() -> Path | None:
    """Scan semua BPR_BIA-<timestamp>.xls di bawah Kirim\\ (rglob, nested per
    bulan/tanggal), pilih yang timestamp-nya (di NAMA FILE, format
    YYYYMMDDHHMMSS, sortable langsung sebagai string) paling besar -- pola sama
    seperti find_latest_toko_gabungan() di omset_seeker.py, nama file lebih
    bisa dipercaya daripada mtime filesystem."""
    if not KIRIM_DIR.exists():
        return None
    candidates = []
    for p in KIRIM_DIR.rglob("BPR_BIA-*.xls"):
        m = _RAW_NAME_RE.match(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]

# Urutan & nama brand PERSIS header kolom H4:Q4 di "Rekap Per DEPO" template
# -- kalau brand baru ditambahkan di raw data tapi belum ada di sini, dia
# tidak akan muncul di kolom manapun (sama seperti Excel: SUMIFS kriteria
# Group Item yang tidak match kolom manapun ya tidak pernah dihitung).
BRAND_COLUMNS = [
    "PROST LAGER", "SINGARAJA PILSNER", "PROST PILSNER", "PROST RAJAWALI LAGER",
    "RAJAWALI FLAVOUR", "ALSTER", "WEISSBIER", "SINGARAJA ARAK", "BAESOMAEK",
    "SINGARAJA PALE ALE",
]

# Daftar tetap (Wilayah, Depo) PERSIS baris B5:C33 template "Rekap Per DEPO"
# -- bukan hasil unique() dari raw data, karena raw data isinya 20 wilayah/47
# depo (cakupan seluruh perusahaan), sedangkan template ini cuma cakupan
# sebagian (DKI/Banten/Bodebek/Jatim/Bali). Perlu diupdate manual di sini
# kalau template sumbernya nambah/kurang baris.
DEPO_AXIS = [
    ("01-DKI", "DP CAKUNG"), ("01-DKI", "DP KAPUK"), ("01-DKI", "DP LEBAK BULUS"),
    ("04-DKI HOREKA", "DP HRK CAKUNG"), ("04-DKI HOREKA", "DP HRK KAPUK"),
    ("04-DKI HOREKA", "DP HRK LEBAK BULUS"),
    ("02-BANTEN", "DP BALARAJA"), ("02-BANTEN", "DP TANGERANG"),
    ("03-BODEBEK", "DP BEKASI"), ("03-BODEBEK", "DP BOGOR"),
    ("08-BANTEN HOREKA", "DP HRK TANGERANG"),
    ("09-BODEBEK HOREKA", "DP HRK BEKASI"), ("09-BODEBEK HOREKA", "DP HRK BOGOR"),
    ("31-JATIM UTARA", "DP GENTENG"), ("31-JATIM UTARA", "DP LUMAJANG"),
    ("31-JATIM UTARA", "DP SURABAYA UTARA"),
    ("33-JATIM SELATAN", "DP BLITAR"), ("33-JATIM SELATAN", "DP MALANG UTARA"),
    ("33-JATIM SELATAN", "DP TUBAN"),
    ("38-JATIM UTARA HOREKA", "DP HRK GENTENG"), ("38-JATIM UTARA HOREKA", "DP HRK LUMAJANG"),
    ("38-JATIM UTARA HOREKA", "HRK SURABAYA"),
    ("39-JATIM SELATAN HOREKA", "DP HRK BLITAR"),
    ("39-JATIM SELATAN HOREKA", "DP HRK MALANG SELATAN"),
    ("39-JATIM SELATAN HOREKA", "DP HRK TUBAN"),
    ("41-BALI", "DP BADUNG"), ("41-BALI", "DP DENPASAR"), ("41-BALI", "DP SINGARAJA"),
    ("48-BALI HOREKA", "DP HRK DENPASAR"),
]

# Pengelompokan region PERSIS urutan baris B5:B22 template "Rekap Per
# WILAYAH" -- tiap region = (wilayah UMUM, wilayah HOREKA-nya), diikuti
# baris subtotal "{REGION} TOTAL".
REGION_MAP = {
    "DKI": ["01-DKI", "04-DKI HOREKA"],
    "BANTEN": ["02-BANTEN", "08-BANTEN HOREKA"],
    "BODEBEK": ["03-BODEBEK", "09-BODEBEK HOREKA"],
    "JATIM UTARA": ["31-JATIM UTARA", "38-JATIM UTARA HOREKA"],
    "JATIM SELATAN": ["33-JATIM SELATAN", "39-JATIM SELATAN HOREKA"],
    "BALI": ["41-BALI", "48-BALI HOREKA"],
}


def load_raw(path) -> pd.DataFrame:
    """Baca sheet 'BPR DETAIL' dari file raw BPR_BIA-<timestamp>.xls lewat
    xlrd langsung (BUKAN pandas.read_excel(engine='xlrd') -- pandas
    mensyaratkan xlrd>=2.0.1 walau file .xls lama tetap terbaca sempurna
    dengan xlrd 1.2.0 yang sudah dipakai di seluruh pipeline ini, lihat
    omset_pipeline/transpose.py). Header sebenarnya di baris Excel ke-2
    (index 1), baris pertama cuma label section kosong-kosong
    ("Requirement", dst)."""
    wb = xlrd.open_workbook(str(path), on_demand=True)
    ws = wb.sheet_by_name(RAW_SHEET)
    header = ws.row_values(1)
    col_names = [str(h).strip() if h else f"_unnamed_{i}" for i, h in enumerate(header)]
    records = [ws.row_values(r) for r in range(2, ws.nrows)]
    df = pd.DataFrame(records, columns=col_names)
    return df[df["SKU_ID"] != ""]


def _safe_div(a, b):
    return a / b if b else 0.0


def compute_rekap_depo(raw: pd.DataFrame) -> pd.DataFrame:
    pos = raw[raw["Proposed Order"] > 0]

    rows = []
    for wilayah, depo in DEPO_AXIS:
        sub_pos = pos[(pos["Wilayah"] == wilayah) & (pos["Destination"] == depo)]
        sub_all = raw[(raw["Wilayah"] == wilayah) & (raw["Destination"] == depo)]

        rec = {
            "Wilayah": wilayah,
            "Depo": depo,
            "NORM": sub_pos["Norm"].sum(),
            "STOK": sub_pos["Stock"].sum(),
            "DOI": sub_pos["DOI"].mean() if not sub_pos.empty else None,
        }
        for brand in BRAND_COLUMNS:
            rec[brand] = sub_all.loc[sub_all["Group Item"] == brand, "Proposed Order"].sum()
        rec["TOTAL"] = sum(rec[b] for b in BRAND_COLUMNS)
        rec["ACTUAL ORDER"] = sub_pos["Actual Order"].sum()
        rec["%"] = _safe_div(rec["ACTUAL ORDER"], rec["TOTAL"])
        rows.append(rec)

    df = pd.DataFrame(rows)

    total = {"Wilayah": None, "Depo": "TOTAL", "DOI": None}
    for col in ["NORM", "STOK"] + BRAND_COLUMNS + ["TOTAL", "ACTUAL ORDER"]:
        total[col] = df[col].sum()
    total["%"] = _safe_div(total["ACTUAL ORDER"], total["TOTAL"])

    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


def compute_rekap_wilayah(raw: pd.DataFrame, rekap_depo: pd.DataFrame) -> pd.DataFrame:
    depo_only = rekap_depo[rekap_depo["Depo"] != "TOTAL"]
    pos = raw[raw["Proposed Order"] > 0]

    rows = []
    for region, wilayahs in REGION_MAP.items():
        region_recs = []
        for wilayah in wilayahs:
            sub = depo_only[depo_only["Wilayah"] == wilayah]
            sub_pos = pos[pos["Wilayah"] == wilayah]

            rec = {
                "Wilayah": wilayah,
                "NORM": sub["NORM"].sum(),
                "STOK": sub["STOK"].sum(),
                "DOI": sub_pos["DOI"].mean() if not sub_pos.empty else None,
            }
            for brand in BRAND_COLUMNS:
                rec[brand] = sub[brand].sum()
            rec["TOTAL"] = sub["TOTAL"].sum()
            rec["ACTUAL ORDER"] = sub["ACTUAL ORDER"].sum()
            rec["%"] = _safe_div(rec["ACTUAL ORDER"], rec["TOTAL"])
            rows.append(rec)
            region_recs.append(rec)

        total = {"Wilayah": f"{region} TOTAL", "DOI": None}
        for col in ["NORM", "STOK"] + BRAND_COLUMNS + ["TOTAL", "ACTUAL ORDER"]:
            total[col] = sum(r[col] for r in region_recs)
        total["%"] = _safe_div(total["ACTUAL ORDER"], total["TOTAL"])
        rows.append(total)

    return pd.DataFrame(rows)
