"""
Transpose OMSHAR per-wilayah -> gabung jadi DAPUL / LAPUL / HOREKA.
Output: XLSX (untuk atasan) + 2 varian CSV per sheet:
  - *_DAPUL.csv          → include 8-baris header (untuk atasan buka di Excel)
  - *_DAPUL_query.csv    → skip header (untuk Python query, lebih cepat load)

Cara kerja:
  - File OMSHAR per brand (mis. OMSHAR UMUM ABIDIN.xls) punya 1 sheet per wilayah
    (BTN, DKI, BDB, JBU, JBS, JTU, JTS, JIU, JIS, BLI, SMU, SMB, SMS, LPB, NTR,
     KLT, KLB, SLS, SLU, PPA), masing-masing 8 baris header + baris data.
  - DAPUL  = header (dari sheet pertama yg ada) + gabungan baris data
             BTN, DKI, BDB, JBU, JBS, JTU, JTS, JIU, JIS, BLI (urut).
  - LAPUL  = header + gabungan baris data SMU, SMB, SMS, LPB, NTR, KLT, KLB,
             SLS, SLU, PPA (urut).
  - HOREKA = header + gabungan baris data 19 wilayah (DAPUL + LAPUL tanpa PPA).
  - Beberapa brand punya >1 file SKU (mis. botol + can), lihat UMUM_FILE/
    HOREKA_FILE. Semua baris dari file-file tersebut di-stack langsung tanpa
    merge -- agregasi per site dilakukan di omset_seeker saat query.
  - Hasil disimpan terpisah per brand ke:
      output/DB TRANSPOSED/UMUM   (XLSX)
      output/DB TRANSPOSED/HOREKA (XLSX)
      output/CSV/UMUM             (CSV atasan + CSV query)
      output/CSV/HOREKA           (CSV atasan + CSV query)
"""

import argparse
from pathlib import Path
from multiprocessing import Pool
import os
import time
import uuid

import xlrd
import openpyxl
import pandas as pd

OMSHAR_DIR = Path(os.environ.get("OMSHAR_DIR",       r"D:\SDAAREA\DB"))
OUTPUT_DIR  = Path(os.environ.get("TRANSPOSE_OUT",   r"D:\SDAAREA\omset_pipeline\output\DB TRANSPOSED"))
CSV_DIR     = Path(os.environ.get("TRANSPOSE_CSV",   r"D:\SDAAREA\omset_pipeline\output\CSV"))

DAPUL  = ['BTN', 'DKI', 'BDB', 'JBU', 'JBS', 'JTU', 'JTS', 'JIU', 'JIS', 'BLI']
LAPUL  = ['SMU', 'SMB', 'SMS', 'LPB', 'NTR', 'KLT', 'KLB', 'SLS', 'SLU', 'PPA']
HOREKA = DAPUL + [w for w in LAPUL if w != 'PPA']

HEADER_ROWS = 8  # baris 1-8 = judul/wilayah/periode/grup + header kolom
COL_SITE = 1
OMSET_COLS = list(range(140, 164))  # EK:FH = JAN 2025 - DES 2026, dipakai saat gabung multi-file per brand

# Kolom KRT 2026 saja -- dipakai buat output "SKU_RAW" (lihat _write_sku_raw_csv()),
# cache per VARIAN SKU individu (bukan per brand gabungan) buat sku_lookup.py supaya
# tidak perlu buka ulang file .xls mentah (~20 detik/file) tiap kali ada query.
COLS_2026 = list(range(152, 164))
MONTH_LABELS_2026 = [
    f"{m} 2026"
    for m in ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGS", "SEP", "OKT", "NOV", "DES"]
]

# 19 SKU + BIR (total kategori) + DIV AB1 (total divisi, paling luas).
# "BEV" TIDAK ditranspose dari file apa pun -- itu dihitung di omset_seeker.py
# sebagai DIV AB1 - BIR.
BRAND_ORDER = [
    "ABIDIN", "AMERAJA", "APIDIN", "SOMAEK",
    "SIMER", "SIJO", "SIDU", "SIRAK",
    "SPA FILTERED", "SPA UNFILTERED", "SINGARAJA",
    "PROST PILSENER", "PROST LAGER", "PRL LAGER",
    "PRL APPLE LIME", "PRL RASPBERRY",
    "PROST ALSTER", "KALTENBERG", "KONIG WEISSBIER", "KONIG DUNKEL",
    "BIR", "DIV AB1",
]

# Brand -> daftar nama file sumber (bisa lebih dari satu varian SKU yang
# digabung jadi satu baris brand, mis. botol Bremer + Can). Saat ada >1 file,
# baris dengan Site sama dari file-file tersebut digabung (sum kolom KRT)
# lewat merge_rows_by_site() -- bukan sekadar ditumpuk mentah.
# Dikonfirmasi lewat pembongkaran formula VLOOKUP asli di
# D:\Random\OMSET OUTLET\OMSET UMUM 2026.xlsx (external link table).
UMUM_FILE = {
    "ABIDIN": ["ABIDIN"],
    "AMERAJA": ["AMERAJA"],
    "APIDIN": ["APIDIN"],
    "SOMAEK": ["GBSM"],
    "SIMER": ["SINGARAJA AMER BREMER", "SINGARAJA AMER CAN"],
    "SIJO": ["SINGARAJA AHI BREMER", "SINGARAJA AHI CAN"],
    "SIDU": ["SINGARAJA ARAK JERUK MADU"],
    "SIRAK": ["SINGARAJA ARAK BREMER"],
    "SPA FILTERED": ["SPAFC320", "SPAFP250"],
    "SPA UNFILTERED": ["SPAUC320", "SPAUP250"],
    "SINGARAJA": ["SINGARAJA"],
    "PROST PILSENER": ["PPIL"],
    "PROST LAGER": ["PLAG"],
    "PRL LAGER": ["PRL"],
    "PRL APPLE LIME": ["RFALP330", "RFALC320"],
    "PRL RASPBERRY": ["RFRBP330", "RPAUC320"],
    "PROST ALSTER": ["PALS"],
    "KALTENBERG": ["KRL"],
    "KONIG WEISSBIER": ["WBR"],
    "KONIG DUNKEL": ["KLW640DK", "KLW330DK"],
    "BIR": ["BIR"],
    "DIV AB1": ["DIV-AB1"],
}

# HOREKA punya konvensi nama file SKU yang berbeda dari UMUM (mis. SIDU
# pakai SAJMP330, bukan "SINGARAJA ARAK JERUK MADU"; PRL RASPBERRY/APPLE LIME
# pakai akhiran 320/330 yang dibalik dari UMUM). Sengaja dibuat dict terpisah
# dari UMUM_FILE (bukan diturunkan/di-share) sesuai permintaan user, supaya
# tiap mode bisa diubah independen ke depannya.
# PRL RASPBERRY & PRL APPLE LIME dikonfirmasi benar lewat pembongkaran formula
# VLOOKUP asli di D:\Random\OMSET OUTLET\OMSET HOREKA 2026.xlsx.
HOREKA_FILE = {
    "ABIDIN": ["ABIDIN"],
    "AMERAJA": ["AMERAJA"],
    "APIDIN": ["APIDIN"],
    "SOMAEK": ["BSM"],
    "SIMER": ["SINGARAJA AMER BREMER", "SINGARAJA AMER CAN"],
    "SIJO": ["SINGARAJA AHI BREMER", "SINGARAJA AHI CAN"],
    "SIDU": ["SAJMP330"],
    "SIRAK": ["SINGARAJA ARAK BREMER"],
    "SPA FILTERED": ["SPAFC320", "SPAFP250"],
    "SPA UNFILTERED": ["SPAUC320", "SPAUP250"],
    "SINGARAJA": ["SINGARAJA"],
    "PROST PILSENER": ["PPIL"],
    "PROST LAGER": ["PLAG"],
    "PRL LAGER": ["PRL"],
    "PRL APPLE LIME": ["RFALP330", "RFALC330"],
    "PRL RASPBERRY": ["RFRBP320", "RPAUC320"],
    "PROST ALSTER": ["PALS"],
    "KALTENBERG": ["KRL"],
    "KONIG WEISSBIER": ["WBR"],
    "KONIG DUNKEL": ["KLW640DK", "KLW330DK"],
    "BIR": ["BIR"],
    "DIV AB1": ["DIV-AB1"],
}

# Varian "WITH KEG" -- HOREKA-only, dipakai outlet yang jual bir keg/draft
# (lihat sheet "WITH KEG" di D:\Random\OMSET OUTLET\OMSET HOREKA 2026.xlsx).
# NOTE: formula asli di file itu menambahkan file KLW640DK (Konig Dunkel) ke
# tiap baris KEG -- itu bug copy-paste (drag-down dari baris KONIG DUNKEL),
# dikonfirmasi user untuk TIDAK direplikasi. Tiap brand KEG di bawah cuma
# dari file sumbernya sendiri.
HOREKA_KEG_BRAND_ORDER = [
    "SINGARAJA KEG 20", "SINGARAJA KEG 30",
    "PROST PILSENER KEG 20", "PROST PILSENER KEG 30",
    "PROST LAGER KEG 20", "PROST LAGER KEG 30",
    "PROST RAJAWALI KEG",
]

HOREKA_KEG_FILE = {
    "SINGARAJA KEG 20": ["SKEG20P"],
    "SINGARAJA KEG 30": ["SKEG30P"],
    "PROST PILSENER KEG 20": ["PKEG20P"],
    "PROST PILSENER KEG 30": ["PKEG30P"],
    "PROST LAGER KEG 20": ["PKEG20L"],
    "PROST LAGER KEG 30": ["PKEG30L"],
    "PROST RAJAWALI KEG": ["RPKEG30L"],
}


# ── CORE TRANSPOSE ────────────────────────────────────────────────────────────

def stack_sheets(wb, sheet_order):
    """Gabungkan baris data dari sheet-sheet wilayah sesuai urutan.

    Header (8 baris pertama) diambil dari sheet pertama yang tersedia.
    Mengembalikan (header_rows, data_rows) atau (None, []) jika tidak
    ada satu pun sheet wilayah yang ditemukan.
    """
    header     = None
    data_rows  = []
    available  = set(wb.sheet_names())

    for name in sheet_order:
        if name not in available:
            continue
        sh = wb.sheet_by_name(name)
        if sh.nrows <= HEADER_ROWS:
            continue

        if header is None:
            header = [
                [sh.cell_value(r, c) for c in range(sh.ncols)]
                for r in range(HEADER_ROWS)
            ]

        ncols = sh.ncols
        for r in range(HEADER_ROWS, sh.nrows):
            row = [sh.cell_value(r, c) for c in range(ncols)]
            if any(v != '' for v in row):
                data_rows.append(row)

    return header, data_rows


def write_stacked_sheet(wb_out, sheet_name, header, data_rows):
    ws = wb_out.create_sheet(title=sheet_name)
    for row in header:
        ws.append(row)
    for row in data_rows:
        ws.append(row)


# ── ATOMIC WRITE ──────────────────────────────────────────────────────────────
# Tulis ke file temp lalu os.replace() ke path final -- kalau proses di-kill
# paksa (mis. lewat Cancel Transpose di Streamlit / taskkill /F /T) di tengah
# nulis, file final yang sudah ada tidak akan ketiban tulisan setengah jadi.

def _replace_with_retry(tmp_path: Path, out_path: Path, attempts: int = 6, delay: float = 0.5) -> None:
    """os.replace() bisa gagal SESAAT dengan PermissionError (WinError 32,
    "process cannot access the file") kalau file .tmp yang baru saja ditulis
    (bisa 40-80MB) masih sempat dikunci sebentar oleh proses lain -- paling
    sering Windows Defender/antivirus real-time scan yang otomatis scan file
    besar yang baru dibuat. Lock semacam ini biasanya lepas dalam <1-2 detik,
    jadi retry singkat cukup -- bukan bug logika, murni race dengan OS/AV."""
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, out_path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _atomic_write(out_path: Path, write_fn) -> None:
    tmp_path = out_path.with_name(f".{out_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_fn(tmp_path)
        _replace_with_retry(tmp_path, out_path)
    finally:
        # Kalau _replace_with_retry() di atas gagal terus (lock beneran macet,
        # bukan transient), tmp_path juga kemungkinan masih terkunci -- jangan
        # biarkan unlink() di sini melempar PermissionError BARU yang menutupi
        # exception ASLI dari _replace_with_retry(). File .tmp yang tersisa
        # tidak berbahaya (nama-nya diawali "." + uuid unik, tidak akan pernah
        # kebaca sebagai output final oleh apa pun).
        try:
            tmp_path.unlink(missing_ok=True)
        except PermissionError:
            pass


# ── CSV EXPORT ────────────────────────────────────────────────────────────────

def save_csv_dual(xlsx_path: Path, csv_subdir: Path):
    """
    Dari XLSX hasil transpose, buat 2 CSV per sheet:
      - <stem>_<SHEET>.csv        → include header (untuk atasan)
      - <stem>_<SHEET>_query.csv  → skip header   (untuk Python query)
    """
    csv_subdir.mkdir(parents=True, exist_ok=True)
    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")

    for sheet in xl.sheet_names:
        # --- untuk atasan: header ikut ---
        df_full = pd.read_excel(
            xl,
            sheet_name=sheet,
            header=None,   # baca mentah, tidak parse header
            dtype=str,     # jaga format string (site number, dsb)
        )
        csv_full = csv_subdir / f"{xlsx_path.stem}_{sheet}.csv"
        _atomic_write(csv_full, lambda p: df_full.to_csv(p, index=False, header=False, encoding="utf-8-sig"))
        print(f"    -> CSV (atasan) : {csv_full.name}")

        # --- untuk Python query: skip 8 baris header ---
        df_query = df_full.iloc[HEADER_ROWS:].reset_index(drop=True)
        csv_query = csv_subdir / f"{xlsx_path.stem}_{sheet}_query.csv"
        _atomic_write(csv_query, lambda p: df_query.to_csv(p, index=False, header=False, encoding="utf-8-sig"))
        print(f"    -> CSV (query)  : {csv_query.name}")


# ── SKU RAW CACHE ─────────────────────────────────────────────────────────────
# CSV ringan (Site + 12 bulan 2026 saja) per VARIAN SKU individu -- ditulis dari
# `rows` yang SUDAH ada di memori dari stack_sheets() di process_brand(), jadi
# tidak ada biaya buka file tambahan. Konsumen: sku_lookup.py (cek klaim per SKU).

def write_sku_raw_csv(omshar_type: str, file_name: str, rows: list, out_subdir: str) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    needed = [COL_SITE] + COLS_2026
    if df.shape[1] <= max(needed):
        print(f"  [WARN] SKU_RAW {file_name}: kolom tidak lengkap, di-skip")
        return
    out = df[needed].copy()
    out.columns = ["Site"] + MONTH_LABELS_2026
    out["Site"] = out["Site"].astype(str).str.strip()

    out_dir = CSV_DIR / out_subdir / "SKU_RAW"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{file_name}.csv"
    _atomic_write(out_path, lambda p: out.to_csv(p, index=False, encoding="utf-8-sig"))
    print(f"  SKU_RAW : {out_path.name} ({len(out)} baris)")


# ── PROCESS PER BRAND ─────────────────────────────────────────────────────────

def process_brand(omshar_type, brand, file_map, groups, out_subdir):
    file_names = file_map.get(brand)
    if not file_names:
        return None

    file_wbs = []  # [(file_name, wb), ...] -- pasangan dipertahankan (bukan list wbs
                   # terpisah) supaya baris tiap file bisa diatribusikan balik ke nama
                   # SKU aslinya buat output SKU_RAW di bawah.
    for file_name in file_names:
        src_path = OMSHAR_DIR / f"OMSHAR {omshar_type} {file_name}.xls"
        if not src_path.exists():
            print(f"  [WARN] {brand}: file tidak ditemukan ({src_path.name})")
            continue
        file_wbs.append((file_name, xlrd.open_workbook(str(src_path), on_demand=True)))

    if not file_wbs:
        print(f"  [SKIP] {brand}: tidak ada file sumber yang ditemukan")
        return None

    wb_out = openpyxl.Workbook(write_only=True)
    per_file_rows = {file_name: [] for file_name, _ in file_wbs}

    wrote_any = False
    for sheet_name, sheet_order in groups:
        header = None
        combined_rows = []
        for file_name, wb_in in file_wbs:
            h, rows = stack_sheets(wb_in, sheet_order)
            if h is None:
                continue
            if header is None:
                header = h
            combined_rows.extend(rows)
            per_file_rows[file_name].extend(rows)

        if header is None:
            print(f"  [SKIP] {brand} {sheet_name}: tidak ada sheet wilayah")
            continue

        write_stacked_sheet(wb_out, sheet_name, header, combined_rows)
        suffix = f" (gabungan {len(file_wbs)} file)" if len(file_wbs) > 1 else ""
        print(f"  {brand} {sheet_name}: {len(combined_rows)} baris{suffix}")
        wrote_any = True

    for _, wb_in in file_wbs:
        wb_in.release_resources()

    for file_name, rows in per_file_rows.items():
        write_sku_raw_csv(omshar_type, file_name, rows, out_subdir)

    if not wrote_any:
        return None

    # Simpan XLSX
    out_dir = OUTPUT_DIR / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"OMSHAR {omshar_type} {brand} TRANSPOSED.xlsx"
    _atomic_write(out_path, wb_out.save)
    print(f"  Tersimpan XLSX : {out_path.name}")

    # Simpan CSV (dual: atasan + query)
    csv_subdir = CSV_DIR / out_subdir
    save_csv_dual(out_path, csv_subdir)

    return out_path


# ── RUN MODES ─────────────────────────────────────────────────────────────────

_WORKER_FAILED = "__WORKER_FAILED__"  # sentinel -- beda dari None (yang berarti "skip", bukan gagal)


def _brand_worker(args):
    """Top-level worker untuk multiprocessing.Pool — harus di luar fungsi lain.

    Tangkap exception per-brand di sini, JANGAN biarkan lolos ke pool.map(): kalau
    satu brand gagal (mis. PermissionError transient dari _atomic_write yang sudah
    habis semua retry-nya) dan exception itu sampai ke pool.map(), SELURUH batch
    berhenti seketika -- brand lain yang sudah/sedang selesai dengan baik pun ikut
    tidak pernah dilaporkan. Brand yang gagal cukup dilaporkan lalu batch lanjut.
    Sentinel _WORKER_FAILED dipakai (bukan None) karena process_brand() sendiri
    sudah pakai None secara sah buat "SKIP, file sumber tidak ada" -- jangan
    disamakan dengan gagal beneran di ringkasan akhir."""
    omshar_type, brand, *_ = args
    try:
        return process_brand(*args)
    except Exception as e:
        print(f"  [GAGAL] {omshar_type} {brand}: {type(e).__name__}: {e}")
        return _WORKER_FAILED


def _run_pool(args, label):
    n_workers = min(4, len(args))
    print(f"  Paralel: {n_workers} proses untuk {len(args)} brand (output mungkin bercampur)\n")
    with Pool(processes=n_workers) as pool:
        results = pool.map(_brand_worker, args)
    failed = [a[1] for a, r in zip(args, results) if r == _WORKER_FAILED]
    if failed:
        print(f"\n  [WARN] {label}: {len(failed)}/{len(args)} brand GAGAL (lihat [GAGAL] di atas): {', '.join(failed)}")


def run_umum():
    print("=== TRANSPOSE UMUM (DAPUL + LAPUL) ===")
    groups = [("DAPUL", DAPUL), ("LAPUL", LAPUL)]
    args = [("UMUM", brand, UMUM_FILE, groups, "UMUM") for brand in BRAND_ORDER]
    _run_pool(args, "UMUM")


def run_horeka():
    print("=== TRANSPOSE HOREKA (19 wilayah) ===")
    groups = [("HOREKA", HOREKA)]
    args = [("HOREKA", brand, HOREKA_FILE, groups, "HOREKA") for brand in BRAND_ORDER]
    _run_pool(args, "HOREKA")


def run_horeka_keg():
    print("=== TRANSPOSE HOREKA WITH KEG (7 brand tambahan) ===")
    groups = [("HOREKA", HOREKA)]
    args = [("HOREKA", brand, HOREKA_KEG_FILE, groups, "HOREKA") for brand in HOREKA_KEG_BRAND_ORDER]
    _run_pool(args, "HOREKA WITH KEG")


def main():
    parser = argparse.ArgumentParser(
        description="Transpose OMSHAR per wilayah jadi DAPUL/LAPUL/HOREKA + export CSV"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default=None,
        choices=["umum", "horeka", "all"],
    )
    args = parser.parse_args()

    mode = args.mode
    if mode is None:
        print("Pilih mode transpose:")
        print("  [1] UMUM")
        print("  [2] HOREKA")
        print("  [3] ALL (UMUM + HOREKA)")
        pilihan = input("Pilihan (1/2/3): ").strip()
        mode = {"1": "umum", "2": "horeka", "3": "all"}.get(pilihan)
        if mode is None:
            print("Pilihan tidak dikenali, dibatalkan.")
            return

    if mode in ("umum", "all"):
        run_umum()
    if mode in ("horeka", "all"):
        run_horeka()
        run_horeka_keg()

    print(f"\nSelesai.")
    print(f"  XLSX : {OUTPUT_DIR}")
    print(f"  CSV  : {CSV_DIR}")


if __name__ == "__main__":
    main()