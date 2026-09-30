"""
OMSHAR90 PIPELINE (WIP -- step 1 dari beberapa)
Baca arsip "OMSHAR 90" (nasional) dari Google Drive -- BEDA dari pipeline
OMSHAR biasa (omset_pipeline/transpose.py):

  - Cakupan NASIONAL, bukan per-wilayah -- kolom "Wil" ada DI DALAM data tiap
    baris, bukan jadi pemisah sheet (OMSHAR biasa: 1 sheet = 1 wilayah).
  - Satu sheet = satu kode item/kelompok brand (mis. "PL-GPLAG",
    "1298-SKC500P"), bukan satu wilayah.
  - Header 3 BARIS (bukan 8 baris flat seperti OMSHAR biasa): baris label
    periode (mis. "JAN 2026") -> baris kategori ("Omset"/"Retur") -> baris
    satuan ("QTY"/"RP"). Tiap periode py QTY *dan* RP, OMSHAR biasa cuma 1
    angka (KRT) per bulan.
  - Retur dilacak terpisah dari Omset (OMSHAR biasa tidak punya konsep ini
    sama sekali).
  - File di Drive TIDAK bertimestamp (tidak seperti BPR_BIA-<ts>.7z) -- Apps
    Script sumbernya menimpa file yang SAMA tiap jalan, jadi Drive cuma
    pernah menyimpan SATU snapshot (hari ini), bukan riwayat harian yang
    menumpuk. Riwayat, kalau dibutuhkan nanti, harus di-backup sendiri oleh
    app ini setiap baca (pola sama seperti bpr_pipeline.backup_to_local()) --
    BELUM diimplementasikan di step ini.
  - Trigger waktunya TIDAK tentu (beda dari BPR yang ~07:00) -- jangan
    asumsikan jam tertentu, cukup baca file yang ADA sekarang.
  - PERIODE di header (mis. "PERIODE : JAN sd 28/09/2026") adalah H+0 nominal,
    TAPI datanya sebenarnya H-1 -- dikonfirmasi user: kalau file bilang
    tanggal 28, data aktualnya representasi tanggal 27. Lihat
    `data_as_of_date()`.
"""

import re
import tempfile
from pathlib import Path

import pandas as pd
import py7zr
import xlrd

from core import paths

ARCHIVE_DIR = paths.GDRIVE_OMSHAR90_DIR
BACKUP_DIR = paths.OMSHAR90_BACKUP_DIR

_MONTH_ABBR_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Nama file arsip TETAP (tidak bertimestamp) -- lihat docstring modul.
ARCHIVE_NAMES = {
    "BEV_BC": "Omset Bev B&C.7z",
    "DIV_AB1": "Omset DIV AB1.7z",
    "FABS_PROST": "Omset Fabs&Prost.7z",
}

HEADER_ROW_LABEL = 5   # baris label periode (mis. "JAN 2026", "RT2 2025")
HEADER_ROW_KIND = 6    # baris kategori ("Omset" / "Retur")
HEADER_ROW_UNIT = 7    # baris satuan ("QTY" / "RP")
DATA_START_ROW = 8

# [FIX] Posisi kolom identitas TIDAK SAMA di semua file -- ditemukan nyata:
# file PROST/FABS/BEV cuma punya 1 kolom "LL FISIK" sebelum Kat/Klas/KeyAcc,
# tapi file "omshar90 DIV AB1'26.xls" (172 sheet) punya 2 kolom di posisi itu
# ("Strata Rp" + "Strata Qty"), jadi Kat/Klas/KeyAcc geser 1 posisi ke kanan.
# Hardcode index (versi lama) diam-diam salah baca KeyAcc jadi nilai Klas
# untuk file DIV AB1 -- SEKARANG dicari by NAMA dari baris header (row index
# HEADER_ROW_LABEL) tiap sheet, bukan posisi tetap, jadi aman dari file mana
# pun urutan kolomnya berbeda.
ID_COL_NAMES = ["Wil", "Site", "Cust", "Kat", "Klas", "KeyAcc"]

_PERIODE_RE = re.compile(r"PERIODE\s*:\s*\w+\s+sd\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)


def find_archives() -> dict[str, Path]:
    """{key: path} untuk arsip yang BENAR-BENAR ada sekarang di Drive --
    key yang filenya belum muncul (mis. Apps Script belum jalan hari ini)
    tidak ikut di dict, BUKAN error."""
    return {
        key: ARCHIVE_DIR / name
        for key, name in ARCHIVE_NAMES.items()
        if (ARCHIVE_DIR / name).exists()
    }


def _extract_periode_text(ws) -> str | None:
    for r in range(4):
        val = ws.cell_value(r, 0)
        if val and "PERIODE" in str(val).upper():
            return str(val)
    return None


def data_as_of_date(ws):
    """Tanggal H-1 dari baris 'PERIODE : ... sd DD/MM/YYYY' -- dikonfirmasi
    user: PERIODE di header itu H+0 nominal, data aktualnya H-1. None kalau
    baris PERIODE tidak ketemu/gagal parse (jangan tebak)."""
    import datetime

    text = _extract_periode_text(ws)
    if text is None:
        return None
    m = _PERIODE_RE.search(text)
    if m is None:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime.date(y, mo, d) - datetime.timedelta(days=1)
    except ValueError:
        return None


def _find_period_columns(header_unit: list) -> list[tuple[int, int]]:
    """Tiap kolom 'QTY' SELALU langsung diikuti 'RP' di kolom sebelahnya --
    dikonfirmasi lewat pembongkaran header asli (bukan tebakan), jadi cukup
    scan baris satuan cari pasangan (QTY, RP) yang bersebelahan -- tidak
    perlu forward-fill baris label yang sparse."""
    pairs = []
    n = len(header_unit)
    for i in range(n - 1):
        if str(header_unit[i]).strip() == "QTY" and str(header_unit[i + 1]).strip() == "RP":
            pairs.append((i, i + 1))
    return pairs


def _find_id_columns(label_row: list) -> dict[str, int]:
    """Cari posisi kolom identitas BY NAMA dari baris header -- lihat
    catatan ID_COL_NAMES kenapa ini tidak boleh posisi tetap."""
    positions = {}
    for i, val in enumerate(label_row):
        name = str(val).strip() if val is not None else ""
        if name in ID_COL_NAMES and name not in positions:
            positions[name] = i
    return positions


def read_sheet(ws, item_code: str, source_file: str) -> pd.DataFrame:
    """Satu sheet = satu item/kelompok brand -- baca semua baris outlet +
    semua periode (Omset & Retur, QTY & RP) jadi satu DataFrame lebar
    (1 baris = 1 outlet, kolom = "{Omset|Retur}_{label periode}_{QTY|RP}")."""
    label_row = ws.row_values(HEADER_ROW_LABEL)
    kind_row = ws.row_values(HEADER_ROW_KIND)
    unit_row = ws.row_values(HEADER_ROW_UNIT)

    id_cols = _find_id_columns(label_row)
    if "Site" not in id_cols:
        raise ValueError(f"Kolom 'Site' tidak ketemu di header sheet '{item_code}'")

    periods = []  # (qty_col, rp_col, "Omset"/"Retur", "JAN 2026"/dst)
    for qty_i, rp_i in _find_period_columns(unit_row):
        label = str(label_row[qty_i]).strip()
        kind = str(kind_row[qty_i]).strip()
        if not label or not kind:
            continue
        periods.append((qty_i, rp_i, kind, label))

    records = []
    for r in range(DATA_START_ROW, ws.nrows):
        row = ws.row_values(r)
        if not row[id_cols["Site"]]:
            continue
        rec = {name: row[idx] for name, idx in id_cols.items()}
        rec["Site"] = str(rec["Site"]).strip()
        rec["item_code"] = item_code
        rec["source_file"] = source_file
        for qty_i, rp_i, kind, label in periods:
            rec[f"{kind}_{label}_QTY"] = row[qty_i]
            rec[f"{kind}_{label}_RP"] = row[rp_i]
        records.append(rec)

    return pd.DataFrame(records)


def read_xls_all_sheets(path: Path, source_file: str) -> pd.DataFrame:
    """Semua sheet dalam SATU file .xls, digabung jadi satu DataFrame
    (kolom item_code membedakan asal tiap baris)."""
    wb = xlrd.open_workbook(str(path), on_demand=True)
    frames = []
    for sheet_name in wb.sheet_names():
        ws = wb.sheet_by_name(sheet_name)
        if ws.nrows <= DATA_START_ROW:
            continue
        try:
            df = read_sheet(ws, sheet_name, source_file)
        except Exception as e:
            print(f"  [SKIP] {source_file} :: {sheet_name}: {type(e).__name__}: {e}")
            continue
        if not df.empty:
            frames.append(df)
    wb.release_resources()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_data(archive_key: str = "DIV_AB1") -> pd.DataFrame:
    """Baca brand-total (read_brand_totals()) dari SATU arsip -- default
    DIV_AB1 (cakupan paling lengkap, 35 brand). Arsip DIV_AB1 sendiri berisi
    BANYAK file .xls (file gabungan "omshar90 ..." + 22 file per-brand
    "OmsharItem-NAS-*") -- yang dipakai adalah file gabungan "omshar90 ...",
    BUKAN file .xls pertama yang kebetulan ketemu di arsip. Return DataFrame
    kosong (bukan error) kalau arsip belum ada di Drive hari ini."""
    archives = find_archives()
    path = archives.get(archive_key)
    if path is None:
        return pd.DataFrame()

    with py7zr.SevenZipFile(path, mode="r") as z:
        names = z.getnames()
        xls_name = next((n for n in names if n.lower().startswith("omshar90")), None)
        if xls_name is None:
            xls_name = next((n for n in names if n.lower().endswith(".xls")), None)
        if xls_name is None:
            return pd.DataFrame()
        with tempfile.TemporaryDirectory() as tmp_dir:
            z.extract(path=tmp_dir, targets=[xls_name])
            return read_brand_totals(Path(tmp_dir) / xls_name, xls_name)


# Sheet TOTAL brand (mis. "PL-GPLAG", "SR-GSINGARAJA") -- diikuti sheet SKU
# individual di bawahnya sampai sheet grup berikutnya (dikonfirmasi lewat
# GRUP/KLPK/ITEM/DIV di header tiap sheet, bukan tebakan). Rekap per Key
# Account/Outlet HARUS pakai sheet ini SAJA -- kalau ikut sheet SKU individual
# juga, angkanya dobel (SKU individual sudah termasuk dalam total grupnya).
#
# [PENTING] File "omshar90 DIV AB1'26.xls" (172 sheet) punya SATU LAPIS
# HIERARKI LAGI yang tidak ada di file PROST/FABS/BEV yang lebih kecil: sheet
# berprefix "GG" (mis. "GGPR-GPROST") adalah TOTAL KATEGORI yang menaungi
# BEBERAPA sheet brand sekaligus (mis. GGPR-GPROST menaungi PL-GPLAG,
# PA-GPALS, dst) -- dicoba dicocokkan manual (jumlah brand yang kelihatan
# masuk akal vs total GGPR), TIDAK ketemu kombinasi yang pas persis, jadi
# batas sheet MANA SAJA yang masuk satu kategori GG belum bisa dipastikan
# tanpa tebak-tebak. Makanya sheet "GG*" DIKECUALIKAN SAMA SEKALI dari rekap
# (bukan cuma "TTL*") -- lebih aman kehilangan level subtotal kategori
# daripada diam-diam dobel-hitung brand yang sudah masuk sheet leaf-nya.
_BRAND_GROUP_SHEET_RE = re.compile(r"^[A-Z0-9]{2,5}-G")


def is_brand_group_sheet(sheet_name: str) -> bool:
    upper = sheet_name.upper()
    if upper.startswith("TTL") or upper.startswith("GG"):
        return False
    return bool(_BRAND_GROUP_SHEET_RE.match(sheet_name))


def read_brand_totals(path: Path, source_file: str) -> pd.DataFrame:
    """Sama seperti read_xls_all_sheets(), TAPI cuma sheet TOTAL brand
    (is_brand_group_sheet()) -- ini yang aman dipakai untuk rekap Key
    Account/Outlet tanpa dobel-hitung. Sheet "TTL <brand>" (grand total
    seluruh file) SENGAJA dikecualikan juga -- itu sendiri sudah jumlah dari
    semua brand group, bukan satu brand."""
    wb = xlrd.open_workbook(str(path), on_demand=True)
    frames = []
    for sheet_name in wb.sheet_names():
        if not is_brand_group_sheet(sheet_name):
            continue
        ws = wb.sheet_by_name(sheet_name)
        if ws.nrows <= DATA_START_ROW:
            continue
        try:
            df = read_sheet(ws, sheet_name, source_file)
        except Exception as e:
            print(f"  [SKIP] {source_file} :: {sheet_name}: {type(e).__name__}: {e}")
            continue
        if not df.empty:
            frames.append(df)
    wb.release_resources()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def compute_rekap_key_account(df: pd.DataFrame) -> pd.DataFrame:
    """Rekap per (KeyAcc, item_code=brand) -- jumlahkan semua kolom
    Omset/Retur QTY & RP lintas outlet dalam key account yang sama. `df`
    HARUS berasal dari read_brand_totals() (bukan read_xls_all_sheets()),
    supaya tidak dobel-hitung SKU individual di dalam total brand-nya."""
    if df.empty:
        return df
    period_cols = [c for c in df.columns if c.startswith("Omset_") or c.startswith("Retur_")]
    grouped = df.groupby(["KeyAcc", "item_code"], as_index=False)[period_cols].sum()
    return grouped.sort_values(["KeyAcc", "item_code"]).reset_index(drop=True)


def compute_rekap_outlet(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """Breakdown per brand untuk SATU outlet -- `df` HARUS dari
    read_brand_totals() (lihat compute_rekap_key_account()). Beda dari
    compute_rekap_key_account(): tidak perlu groupby (1 outlet = 1 baris
    per brand sudah unik), tapi kolom identitas (Cust/Wil/dst) ikut
    dipertahankan karena cuma 1 outlet, bukan agregat banyak outlet."""
    if df.empty:
        return df
    sub = df[df["Site"] == site]
    id_cols = ["Site", "Cust", "Wil", "Kat", "Klas", "KeyAcc", "item_code"]
    period_cols = [c for c in df.columns if c.startswith("Omset_") or c.startswith("Retur_")]
    return sub[[c for c in id_cols if c in sub.columns] + period_cols].reset_index(drop=True)


def peek_as_of_date(archive_path: Path):
    """Baca tanggal H-1 dari SATU sheet SATU file di dalam arsip -- cukup
    untuk tahu tanggal datanya tanpa perlu ekstrak seluruh arsip (arsip DIV
    AB1 sendiri ~150MB kalau diekstrak penuh). Semua file dalam 1 arsip
    ditarik di run Apps Script yang sama, jadi tanggalnya pasti sama untuk
    arsip itu -- cukup 1 sheet 1 file yang dicek."""
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as z:
            xls_name = next((n for n in z.getnames() if n.lower().endswith(".xls")), None)
            if xls_name is None:
                return None
            with tempfile.TemporaryDirectory() as tmp_dir:
                z.extract(path=tmp_dir, targets=[xls_name])
                wb = xlrd.open_workbook(str(Path(tmp_dir) / xls_name), on_demand=True)
                as_of = data_as_of_date(wb.sheet_by_index(0))
                wb.release_resources()
                return as_of
    except Exception:
        return None


def _closing_folder_for(year: int, month: int) -> Path:
    """Folder backup bulanan -- konvensi 'Closing <Mon> <Year>\\' SUDAH
    dipakai manual di BACKUP_DIR sebelum pipeline ini ada (dikonfirmasi
    langsung dari isi foldernya: 'Closing Sep 2026', 'Closing Aug 2026',
    dst -- bukan bikin konvensi baru)."""
    return BACKUP_DIR / f"Closing {_MONTH_ABBR_EN[month]} {year}"


def backup_monthly() -> dict:
    """Backup RAW (semua file DI DALAM ketiga arsip, apa adanya, tidak
    diproses) ke folder Closing <bulan data> <tahun> -- SEKALI per bulan.
    Idempotent: kalau folder bulan itu sudah ada isinya, TIDAK diekstrak
    ulang (arsip Drive tidak bertimestamp/tidak menumpuk, lihat docstring
    modul -- jadi tidak ada 'versi lebih baru' yang perlu dicek per hari,
    beda dari bpr_pipeline.backup_to_local() yang checknya per file per hari).

    Best-effort per arsip -- satu arsip gagal tidak menghentikan yang lain
    ATAU membuat pemanggil (halaman utama) gagal, sama seperti
    bpr_pipeline.backup_to_local()."""
    archives = find_archives()
    if not archives:
        return {"done": False, "reason": "no_archive"}

    as_of = None
    for path in archives.values():
        as_of = peek_as_of_date(path)
        if as_of is not None:
            break
    if as_of is None:
        return {"done": False, "reason": "no_periode_date"}

    target_dir = _closing_folder_for(as_of.year, as_of.month)
    if target_dir.exists() and any(target_dir.iterdir()):
        return {"done": False, "reason": "already_backed_up", "target": target_dir, "as_of": as_of}

    target_dir.mkdir(parents=True, exist_ok=True)
    extracted_keys = []
    for key, path in archives.items():
        try:
            with py7zr.SevenZipFile(path, mode="r") as z:
                z.extractall(path=target_dir)
            extracted_keys.append(key)
        except Exception as e:
            print(f"[WARN] backup_monthly: gagal ekstrak {key} ({path.name}): {type(e).__name__}: {e}")

    return {"done": True, "target": target_dir, "as_of": as_of, "extracted": extracted_keys}
