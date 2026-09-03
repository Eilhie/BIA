"""
Transpose OMSHAR per-wilayah -> gabung jadi DAPUL / LAPUL / HOREKA.
Output: XLSX (untuk atasan) + 2 varian CSV per sheet:
  - *_DAPUL.csv          → include 8-baris header (untuk atasan buka di Excel)
  - *_DAPUL_query.csv    → skip header (untuk Python query, lebih cepat load)

Cara kerja:
  - File OMSHAR per brand (mis. OMSHAR UMUM ABIDIN.xls) punya 1 sheet per wilayah
    (BTN, DKI, BDB, JBU, JBS, JTU, JTS, JIU, JIS, BLI, SMU, SMB, SMS, LPB, NTR,
     KLT, KLB, SLS, SLU, PPA), masing-masing 8 baris header + baris data.
  - DAPUL  = header (dari sheet dengan PERIODE paling baru) + gabungan baris data
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

CATATAN PERUBAHAN (lihat masing-masing bagian bertanda [OPT]):
  1. Mode "all" sekarang pakai SATU Pool gabungan (bukan 3 Pool berurutan),
     dengan jumlah worker di-cap ke jumlah core CPU (default 12, tapi tetap
     dibatasi os.cpu_count()).
  2. CSV ditulis langsung dari `header`/`combined_rows` yang sudah ada di
     memori saat proses per-brand -- tidak lagi re-open XLSX yang baru saja
     ditulis (menghapus round-trip openpyxl -> pandas.read_excel).
     PENTING: verifikasi ekuivalensi output vs versi lama sebelum dipakai
     produksi (lihat catatan di write_csv_dual_from_rows()).
  3. get_file_cutoffs_parallel() -- paralelkan lewat SUBPROCESS python
     terpisah (pola sama seperti run_umum() dkk yang sudah aman), dengan
     fallback otomatis ke versi serial (get_file_cutoffs()) kalau subprocess
     gagal untuk alasan apa pun.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import uuid
from multiprocessing import Pool
from pathlib import Path

import xlrd
import openpyxl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

OMSHAR_DIR = Path(os.environ.get("OMSHAR_DIR",     str(_PROJECT_ROOT / "DB")))
OUTPUT_DIR  = Path(os.environ.get("TRANSPOSE_OUT", str(_PROJECT_ROOT / "omset_pipeline" / "output" / "DB TRANSPOSED")))
CSV_DIR     = Path(os.environ.get("TRANSPOSE_CSV", str(_PROJECT_ROOT / "omset_pipeline" / "output" / "CSV")))

DAPUL  = ['BTN', 'DKI', 'BDB', 'JBU', 'JBS', 'JTU', 'JTS', 'JIU', 'JIS', 'BLI']
LAPUL  = ['SMU', 'SMB', 'SMS', 'LPB', 'NTR', 'KLT', 'KLB', 'SLS', 'SLU', 'PPA']
HOREKA = DAPUL + [w for w in LAPUL if w != 'PPA']

HEADER_ROWS = 8  # baris 1-8 = judul/wilayah/periode/grup + header kolom
COL_SITE = 1
OMSET_COLS = list(range(140, 164))  # EK:FH = JAN 2025 - DES 2026, dipakai saat gabung multi-file per brand

# Kolom KRT 2025 & 2026 -- dipakai buat output "SKU_RAW" (lihat write_sku_raw_csv()),
# cache per VARIAN SKU individu (bukan per brand gabungan) buat sku_lookup.py supaya
# tidak perlu buka ulang file .xls mentah (~20 detik/file) tiap kali ada query. Dua
# tahun sekaligus (bukan cuma 2026) supaya Detail SKU Brand Besar bisa tampilkan
# RT2 25/RT2 26 persis format Omset Seeker, bukan cuma trend 2026 saja.
_MONTHS_ID = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGS", "SEP", "OKT", "NOV", "DES"]
COLS_2025 = list(range(140, 152))
MONTH_LABELS_2025 = [f"{m} 2025" for m in _MONTHS_ID]
COLS_2026 = list(range(152, 164))
MONTH_LABELS_2026 = [f"{m} 2026" for m in _MONTHS_ID]

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
# KEG 10 & PET 20L -- SKU baru (belum ada di server saat ditambahkan, per cek
# langsung ke DEST_DB + SKU_LIST), ditambahkan sebagai fallback siap pakai:
# process_brand() sudah otomatis skip (bukan gagal) kalau file sumbernya
# belum ada, jadi aman ditambahkan sekarang -- begitu SKU-nya benar-benar
# disync, langsung ikut ditranspose tanpa perlu ubah kode lagi.
HOREKA_KEG_BRAND_ORDER = [
    "SINGARAJA KEG 10", "SINGARAJA KEG 20", "SINGARAJA KEG 30",
    "PROST PILSENER KEG 10", "PROST PILSENER KEG 20", "PROST PILSENER KEG 30",
    "PROST LAGER KEG 10", "PROST LAGER KEG 20", "PROST LAGER KEG 30",
    "PROST RAJAWALI KEG 10", "PROST RAJAWALI KEG 30",
    "SINGARAJA PET 20L", "PROST PILSENER PET 20L", "PROST LAGER PET 20L", "PROST RAJAWALI PET 20L",
]

HOREKA_KEG_FILE = {
    "SINGARAJA KEG 10": ["SKEG10P"],
    "SINGARAJA KEG 20": ["SKEG20P"],
    "SINGARAJA KEG 30": ["SKEG30P"],
    "PROST PILSENER KEG 10": ["PKEG10P"],
    "PROST PILSENER KEG 20": ["PKEG20P"],
    "PROST PILSENER KEG 30": ["PKEG30P"],
    "PROST LAGER KEG 10": ["PKEG10L"],
    "PROST LAGER KEG 20": ["PKEG20L"],
    "PROST LAGER KEG 30": ["PKEG30L"],
    "PROST RAJAWALI KEG 10": ["RPKEG10L"],
    "PROST RAJAWALI KEG 30": ["RPKEG30L"],
    "SINGARAJA PET 20L": ["SPET20P"],
    "PROST PILSENER PET 20L": ["PPET20P"],
    "PROST LAGER PET 20L": ["PPET20L"],
    "PROST RAJAWALI PET 20L": ["RPPET20L"],
}


# ── CORE TRANSPOSE ────────────────────────────────────────────────────────────

def _parse_periode(header_rows) -> tuple | None:
    """Ekstrak (year, month, day) dari baris 'PERIODE : JAN sd DD/MM/YYYY'
    (baris index 2 di header 8-baris) -- tuple diurut (Y,M,D) biar bisa
    dibandingkan langsung ('>' = lebih baru). None kalau gagal parse."""
    try:
        text = str(header_rows[2][0])
        date_part = text.split("sd")[-1].strip()
        d, m, y = date_part.split("/")
        return (int(y), int(m), int(d))
    except Exception:
        return None


def _file_max_periode(path_str: str):
    """Baca PERIODE PALING BARU di antara SEMUA sheet wilayah dalam SATU file
    mentah. xlrd (format .xls lama) tidak bisa baca satu sel tanpa parse
    seluruh sheet lebih dulu -- baca 1 file (~20 sheet wilayah) makan waktu
    ~15-25 detik, dan halaman diagnostik (Cek Cutoff OMSHAR) perlu baca INI
    untuk PULUHAN file sekaligus (lihat get_file_cutoffs() / get_file_cutoffs_parallel())."""
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        wb = xlrd.open_workbook(path_str, on_demand=True)
        best = None
        for name in wb.sheet_names():
            sh = wb.sheet_by_name(name)
            if sh.nrows <= HEADER_ROWS:
                continue
            header = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(HEADER_ROWS)]
            p = _parse_periode(header)
            if p and (best is None or p > best):
                best = p
        wb.release_resources()
        return best
    except Exception:
        return None


def get_file_cutoffs(paths: list[str]) -> dict:
    """Return {path_str: (y,m,d) atau None} untuk banyak file mentah SEKALIGUS,
    SERIAL. Ini fallback aman dipakai get_file_cutoffs_parallel() di bawah --
    lihat docstring di sana untuk alasan kenapa in-process parallel (Pool /
    ThreadPoolExecutor) tidak dipakai di halaman Streamlit manapun."""
    return {p: _file_max_periode(p) for p in paths}


# [OPT-3] Paralelisasi get_file_cutoffs via SUBPROCESS python terpisah.
def _cutoff_worker_main(paths: list[str]) -> None:
    """Entry point saat script ini dipanggil sebagai subprocess worker
    (lihat blok `if __name__ == "__main__"` di bawah). Cetak hasil sebagai
    JSON ke stdout -- proses induk yang parse."""
    result = get_file_cutoffs(paths)
    # tuple bukan JSON-native -> ubah ke list supaya json.dumps aman,
    # nanti di sisi pemanggil diubah balik ke tuple.
    serializable = {p: (list(v) if v is not None else None) for p, v in result.items()}
    print(json.dumps(serializable))


def get_file_cutoffs_parallel(paths: list[str], n_workers: int | None = None, timeout: int = 120) -> dict:
    """Versi paralel dari get_file_cutoffs(), lewat SUBPROCESS python asli
    (bukan multiprocessing.Pool, bukan ThreadPoolExecutor) -- pola yang sama
    dengan run_umum()/run_horeka() yang dipanggil dari
    pages/1_Sync_dan_Transpose.py, karena itu SUDAH terbukti aman: proses OS
    terpisah tidak ikut re-import/re-run halaman Streamlit (beda dengan
    multiprocessing.Pool 'spawn' di Windows), dan tidak kena batasan GIL
    (beda dengan ThreadPoolExecutor, yang percuma untuk kerja CPU-bound
    murni Python seperti parsing xlrd -- lihat catatan lengkap di
    get_file_cutoffs() versi lama / docstring _file_max_periode()).

    Kalau subprocess gagal untuk alasan apa pun (python executable tidak
    ketemu, timeout, dsb), fallback OTOMATIS ke get_file_cutoffs() serial --
    caller tidak perlu tahu/handle bedanya.
    """
    if not paths:
        return {}

    n_workers = min(n_workers or 8, os.cpu_count() or 4, len(paths))
    if n_workers <= 1:
        return get_file_cutoffs(paths)

    chunks = [c for c in (paths[i::n_workers] for i in range(n_workers)) if c]

    try:
        procs = [
            subprocess.Popen(
                [sys.executable, __file__, "_cutoff_worker", *chunk],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for chunk in chunks
        ]

        results: dict = {}
        for p in procs:
            out, err = p.communicate(timeout=timeout)
            if p.returncode != 0:
                raise RuntimeError(f"cutoff worker gagal (code {p.returncode}): {err.strip()}")
            chunk_result = json.loads(out)
            for path_str, val in chunk_result.items():
                results[path_str] = tuple(val) if val is not None else None
        return results

    except Exception as e:
        print(f"[WARN] get_file_cutoffs_parallel gagal ({type(e).__name__}: {e}), fallback ke serial")
        return get_file_cutoffs(paths)


def stack_sheets(wb, sheet_order):
    """Gabungkan baris data dari sheet-sheet wilayah sesuai urutan.

    Header (8 baris pertama) diambil dari sheet dengan PERIODE PALING BARU
    di antara yang tersedia -- BUKAN cuma wilayah pertama di sheet_order.
    Tiap wilayah punya baris PERIODE sendiri-sendiri dan bisa ke-update di
    waktu berbeda (dikonfirmasi nyata: BTN -- selalu wilayah pertama di
    DAPUL/HOREKA -- sering lagging beberapa hari dibanding wilayah lain
    seperti DKI/JBU/SMB, jadi kalau header selalu diambil dari wilayah
    pertama yang tersedia, cutoff yang dilaporkan APLIKASI jadi understated
    walau wilayah lain di file yang sama sudah lebih baru). Fallback ke
    "sheet pertama yang tersedia" tetap dipakai kalau PERIODE-nya gagal
    di-parse di semua sheet.
    Mengembalikan (header_rows, data_rows) atau (None, []) jika tidak
    ada satu pun sheet wilayah yang ditemukan.
    """
    header         = None
    header_periode = None
    data_rows      = []
    available      = set(wb.sheet_names())

    for name in sheet_order:
        if name not in available:
            continue
        sh = wb.sheet_by_name(name)
        if sh.nrows <= HEADER_ROWS:
            continue

        sheet_header = [
            [sh.cell_value(r, c) for c in range(sh.ncols)]
            for r in range(HEADER_ROWS)
        ]
        sheet_periode = _parse_periode(sheet_header)

        if header is None or (sheet_periode is not None
                               and (header_periode is None or sheet_periode > header_periode)):
            header = sheet_header
            header_periode = sheet_periode

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
# [OPT-2] CSV ditulis LANGSUNG dari `header`/`data_rows` yang sudah ada di
# memori (dipanggil dari process_brand() di bawah, per sheet, tepat setelah
# write_stacked_sheet()) -- TIDAK lagi re-open XLSX yang baru saja ditulis
# lewat pandas.read_excel (round-trip openpyxl -> pandas dihapus).
#
# PENTING -- verifikasi ekuivalensi sebelum dipakai produksi:
#   - Versi lama baca ulang lewat pd.read_excel(..., dtype=str), yang
#     memformat angka/tanggal Excel jadi representasi string tertentu.
#     Versi baru menulis nilai mentah dari xlrd.cell_value() (bisa float
#     Python, str, dst) apa adanya via csv.writer.
#   - Untuk sebagian besar kolom (Site, KRT angka) hasilnya biasanya identik,
#     tapi WAJIB diff CSV lama vs baru untuk beberapa brand representatif
#     (mis. yang punya multi-file seperti SIMER/SIJO, dan yang single-file
#     seperti ABIDIN) sebelum menghapus jalur save_csv_dual() lama:
#       diff <(sort old.csv) <(sort new.csv)   # atau bandingkan baris demi baris
#   - Kalau ada selisih format angka, tambahkan normalisasi eksplisit di
#     _write_rows() (mis. format float tertentu) sebelum go-live.

def _write_rows(path: Path, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)


def write_csv_dual_from_rows(csv_subdir: Path, stem: str, sheet_name: str, header: list, data_rows: list) -> None:
    """Tulis 2 CSV per sheet langsung dari data di memori:
      - <stem>_<SHEET>.csv        → include header (untuk atasan)
      - <stem>_<SHEET>_query.csv  → skip header   (untuk Python query)
    """
    csv_subdir.mkdir(parents=True, exist_ok=True)

    csv_full = csv_subdir / f"{stem}_{sheet_name}.csv"
    _atomic_write(csv_full, lambda p: _write_rows(p, header + data_rows))
    print(f"    -> CSV (atasan) : {csv_full.name}")

    csv_query = csv_subdir / f"{stem}_{sheet_name}_query.csv"
    _atomic_write(csv_query, lambda p: _write_rows(p, data_rows))
    print(f"    -> CSV (query)  : {csv_query.name}")


# ── SKU RAW CACHE ─────────────────────────────────────────────────────────────
# CSV ringan (Site + 12 bulan 2025 + 12 bulan 2026) per VARIAN SKU individu --
# ditulis dari `rows` yang SUDAH ada di memori dari stack_sheets() di
# process_brand(), jadi tidak ada biaya buka file tambahan. Konsumen:
# sku_lookup.py (cek klaim per SKU, Detail SKU Brand Besar).

def write_sku_raw_csv(omshar_type: str, file_name: str, rows: list, out_subdir: str) -> None:
    if not rows:
        return
    needed = [COL_SITE] + COLS_2025 + COLS_2026
    max_needed = max(needed)

    out_rows = [["Site"] + MONTH_LABELS_2025 + MONTH_LABELS_2026]
    skipped = False
    for row in rows:
        if len(row) <= max_needed:
            skipped = True
            continue
        site = str(row[COL_SITE]).strip()
        out_rows.append([site] + [row[c] for c in COLS_2025] + [row[c] for c in COLS_2026])

    if skipped and len(out_rows) <= 1:
        print(f"  [WARN] SKU_RAW {file_name}: kolom tidak lengkap, di-skip")
        return

    out_dir = CSV_DIR / out_subdir / "SKU_RAW"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{file_name}.csv"
    _atomic_write(out_path, lambda p: _write_rows(p, out_rows))
    print(f"  SKU_RAW : {out_path.name} ({len(out_rows) - 1} baris)")


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

    stem = f"OMSHAR {omshar_type} {brand} TRANSPOSED"
    csv_subdir = CSV_DIR / out_subdir

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

        # [OPT-2] tulis CSV langsung dari memori, bukan reload XLSX nanti.
        write_csv_dual_from_rows(csv_subdir, stem, sheet_name, header, combined_rows)

        wrote_any = True

    for _, wb_in in file_wbs:
        wb_in.release_resources()

    for file_name, rows in per_file_rows.items():
        write_sku_raw_csv(omshar_type, file_name, rows, out_subdir)

    if not wrote_any:
        return None

    # Simpan XLSX (tetap dibuat -- ini yang dibuka atasan langsung di Excel)
    out_dir = OUTPUT_DIR / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.xlsx"
    _atomic_write(out_path, wb_out.save)
    print(f"  Tersimpan XLSX : {out_path.name}")

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


def _run_pool(args, label, max_workers=20):
    # [OPT-1] Cap ke jumlah core CPU yang benar-benar ada -- oversubscribe
    # di atas core fisik untuk kerja CPU-bound (parsing xlrd) memperlambat,
    # bukan mempercepat (context-switch overhead). max_workers=20 adalah
    # target atas, bukan nilai yang dipaksakan -- dinaikkan dari 12 setelah
    # diukur nyata: 4 proses paralel makan waktu SAMA PERSIS dengan 1 proses
    # sendirian (~225s), jadi tidak ada tanda kontensi I/O/CPU sampai level
    # itu. 20 (bukan 32, jumlah core fisik) sengaja disisakan ruang -- worker
    # terbesar terukur ~756MB RSS (file DIV-AB1/BIR/SINGARAJA), dan proses
    # Transpose ini jalan bareng Streamlit server yang sama, jadi jangan
    # habiskan semua core/RAM cuma buat batch ini.
    n_workers = min(max_workers, os.cpu_count() or max_workers, len(args))
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


def run_custom(omshar_type: str, codes: list[str]):
    """Transpose SKU INDIVIDUAL yang dipilih manual -- isolated dari 59 brand
    rollup di atas (run_umum/run_horeka/run_horeka_keg/run_all), tidak
    menyentuh/mengubah apa pun di sana. Tiap kode diperlakukan sebagai
    "brand" satu-file sendiri (file_map = {code: [code]}), jadi output XLSX/
    CSV-nya bernama kode SKU mentahnya sendiri -- otomatis tidak bentrok nama
    dengan brand rollup asli (nama brand itu label manusia, bukan kode SKU
    mentah). Efek samping yang justru jadi tujuan utama: process_brand()
    menulis SKU_RAW cache per file yang dibaca (lihat write_sku_raw_csv()) --
    begitu kode ini ditranspose sekali lewat sini, Detail SKU Brand Besar
    otomatis dapat jalur cepatnya juga untuk kode itu, tanpa perlu ditambah
    ke UMUM_FILE/HOREKA_FILE (yang mengubah brand ROLLUP resmi -- beda hal)."""
    print(f"=== TRANSPOSE CUSTOM ({omshar_type}, {len(codes)} SKU dipilih manual) ===")
    groups = [("DAPUL", DAPUL), ("LAPUL", LAPUL)] if omshar_type == "UMUM" else [("HOREKA", HOREKA)]
    file_map = {code: [code] for code in codes}
    args = [(omshar_type, code, file_map, groups, omshar_type) for code in codes]
    _run_pool(args, "CUSTOM")


def run_all():
    """[OPT-1] Mode 'all' = SATU Pool gabungan untuk UMUM + HOREKA +
    HOREKA WITH KEG, bukan 3 Pool terpisah berurutan. Menghapus overhead
    spawn Pool 3x dan memungkinkan brand dari mode berbeda diproses
    concurrent selama masih di bawah cap worker."""
    print("=== TRANSPOSE ALL (UMUM + HOREKA + HOREKA WITH KEG) ===")
    groups_umum   = [("DAPUL", DAPUL), ("LAPUL", LAPUL)]
    groups_horeka = [("HOREKA", HOREKA)]

    args = (
        [("UMUM",   brand, UMUM_FILE,      groups_umum,   "UMUM")   for brand in BRAND_ORDER]
        + [("HOREKA", brand, HOREKA_FILE,     groups_horeka, "HOREKA") for brand in BRAND_ORDER]
        + [("HOREKA", brand, HOREKA_KEG_FILE, groups_horeka, "HOREKA") for brand in HOREKA_KEG_BRAND_ORDER]
    )
    _run_pool(args, "ALL")


def main():
    parser = argparse.ArgumentParser(
        description="Transpose OMSHAR per wilayah jadi DAPUL/LAPUL/HOREKA + export CSV"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default=None,
        choices=["umum", "horeka", "horeka_keg", "all"],
    )
    args = parser.parse_args()

    mode = args.mode
    if mode is None:
        print("Pilih mode transpose:")
        print("  [1] UMUM")
        print("  [2] HOREKA")
        print("  [3] HOREKA + KEG/PET")
        print("  [4] ALL (UMUM + HOREKA + KEG/PET)")
        pilihan = input("Pilihan (1/2/3/4): ").strip()
        mode = {"1": "umum", "2": "horeka", "3": "horeka_keg", "4": "all"}.get(pilihan)
        if mode is None:
            print("Pilihan tidak dikenali, dibatalkan.")
            return

    # [OPT-1] mode "all" sekarang lewat run_all() (satu Pool gabungan),
    # bukan run_umum() + run_horeka() + run_horeka_keg() berurutan.
    # "horeka" dan "horeka_keg" sengaja dipisah (bukan selalu dibundel seperti
    # sebelumnya) -- pass KEG/PET tambahan itu ~15 brand ekstra yang tidak
    # semua orang butuh tiap kali transpose HOREKA, jadi dibikin opsional.
    if mode == "all":
        run_all()
    elif mode == "umum":
        run_umum()
    elif mode == "horeka":
        run_horeka()
    elif mode == "horeka_keg":
        run_horeka()
        run_horeka_keg()

    print(f"\nSelesai.")
    print(f"  XLSX : {OUTPUT_DIR}")
    print(f"  CSV  : {CSV_DIR}")


if __name__ == "__main__":
    # [OPT-3] Dispatch khusus: kalau script ini dipanggil sebagai subprocess
    # worker oleh get_file_cutoffs_parallel() (argv[1] == "_cutoff_worker"),
    # jalankan worker itu saja dan keluar -- JANGAN masuk ke main() biasa.
    if len(sys.argv) > 1 and sys.argv[1] == "_cutoff_worker":
        _cutoff_worker_main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "custom":
        # transpose.py custom <UMUM|HOREKA> <CODE1,CODE2,...> -- dispatch khusus
        # sama seperti _cutoff_worker di atas, karena run_custom() butuh 2 argumen
        # tambahan (channel + daftar kode) yang tidak cocok dipaksakan ke argparse
        # "mode" tunggal punya main().
        run_custom(sys.argv[2], [c for c in sys.argv[3].split(",") if c])
    else:
        main()