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

import os
import re
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import py7zr
import xlrd

RAW_SHEET = "BPR DETAIL"

# Sumber ASLI: Google Drive (G:) -- terbukti nyata file .7z masuk otomatis
# tiap ~07:00 pagi TERMASUK weekend (16 file sejak 19 Agustus, termasuk 22 &
# 25 Agustus yang WEEKEND). Folder lokal D:\Data BIA\...\Kirim\ ternyata cuma
# salinan yang diekstrak MANUAL oleh seseorang dari sini -- kadang skip
# weekend, kadang telat -- jadi G: dipakai duluan, D: cuma fallback kalau G:
# (Google Drive Desktop) sedang tidak ke-mount di komputer yang jalanin app.
GDRIVE_BPR_DIR = Path(r"G:\My Drive\BPR BIA")
DAILY_REPORT_DIR = Path(r"D:\Data BIA\2026\Daily Report")
KIRIM_DIR = DAILY_REPORT_DIR / "Kirim"

_ARCHIVE_NAME_RE = re.compile(r"^BPR_BIA-(\d{14})\.7z$")
_RAW_NAME_RE = re.compile(r"^BPR_BIA-(\d{14})\.xls$")
_TS_RE = re.compile(r"BPR_BIA-(\d{14})\.")


def _scan(dir_path: Path, pattern: str, name_re: re.Pattern) -> list[tuple[str, Path]]:
    if not dir_path.exists():
        return []
    out = []
    for p in dir_path.rglob(pattern):
        m = name_re.match(p.name)
        if m:
            out.append((m.group(1), p))
    return out


def find_latest_raw() -> Path | None:
    """Cari BPR_BIA-<timestamp> paling baru -- coba Google Drive (.7z) dulu,
    baru fallback ke arsip lokal D:\\...\\Kirim\\ (.xls) kalau G: tidak
    ke-mount. Timestamp di NAMA FILE (format YYYYMMDDHHMMSS, sortable
    langsung sebagai string) yang dipakai buat bandingkan, bukan mtime --
    pola sama seperti find_latest_toko_gabungan() di omset_seeker.py."""
    candidates = _scan(GDRIVE_BPR_DIR, "BPR_BIA-*.7z", _ARCHIVE_NAME_RE)
    if not candidates:
        candidates = _scan(KIRIM_DIR, "BPR_BIA-*.xls", _RAW_NAME_RE)
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def find_previous_raw(current: Path) -> Path | None:
    """Cari raw PALING BARU SEBELUM `current` (sumber & format sama seperti
    `current` -- .7z di Google Drive kalau current dari sana, .xls lokal
    kalau fallback) -- dipakai buat kolom perbandingan 'TOTAL <tanggal>' (hari
    kerja sebelumnya yang datanya ada, otomatis lompat weekend/hari libur
    kalau memang tidak ada laporan hari itu).

    Template asli punya kolom sejenis ('TOTAL 15 MAY 2026' dst.) tapi lewat
    external link Excel yang di-relink manual -- terbukti nyata sering telat
    beberapa hari. Ini baca raw file historis LANGSUNG, jadi selalu akurat
    tanpa perlu relink apa pun."""
    is_archive = current.suffix == ".7z"
    name_re = _ARCHIVE_NAME_RE if is_archive else _RAW_NAME_RE
    scan_dir = GDRIVE_BPR_DIR if is_archive else KIRIM_DIR
    pattern = "BPR_BIA-*.7z" if is_archive else "BPR_BIA-*.xls"

    m_cur = name_re.match(current.name)
    if m_cur is None:
        return None
    cur_ts = m_cur.group(1)
    candidates = [(ts, p) for ts, p in _scan(scan_dir, pattern, name_re) if ts < cur_ts]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


_MONTH_ABBR_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _local_folder_for(year: int, month: int, day: int) -> Path:
    """Folder kerja lokal buat tanggal ini, ikut pola yang SUDAH dipakai
    sendiri di Kirim\\ (mis. 'Aug - 08\\27 Aug', hari TANPA nol di depan) --
    bukan bikin konvensi baru, biar file yang di-backup nyambung natural ke
    folder yang biasa dibuka manual, bukan folder asing yang beda gaya."""
    month_folder = f"{_MONTH_ABBR_EN[month]} - {month:02d}"
    day_folder = f"{day} {_MONTH_ABBR_EN[month]}"
    return KIRIM_DIR / month_folder / day_folder


def backup_to_local(path: Path) -> tuple[Path, bool] | None:
    """Kalau `path` diambil dari Google Drive (.7z), ekstrak & simpan salinan
    .xls-nya ke folder kerja lokal Kirim\\<bulan>\\<tanggal>\\ -- supaya
    folder kerja harian yang biasa dipakai tetap otomatis ke-isi, tidak lagi
    bergantung ekstrak manual (yang terbukti suka skip weekend/telat).

    Return (path_lokal, True) kalau baru ditulis, (path_lokal, False) kalau
    sudah ada sebelumnya (tidak ditimpa), None kalau bukan .7z (sudah file
    lokal, tidak perlu backup ke diri sendiri) atau gagal.

    Best-effort -- kalau gagal (mis. tidak ada izin tulis, path aneh),
    return None diam-diam, TIDAK boleh bikin halaman utama gagal cuma gara-
    gara backup-nya gagal (backup itu bonus, bukan jalur kritis)."""
    if path.suffix != ".7z":
        return None
    m = _TS_RE.search(path.name)
    if m is None:
        return None
    ts = m.group(1)
    y, mo, d = int(ts[:4]), int(ts[4:6]), int(ts[6:8])
    target_dir = _local_folder_for(y, mo, d)
    target_path = target_dir / f"BPR_BIA-{ts}.xls"
    if target_path.exists():
        return target_path, False

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(path, mode="r") as z:
            xls_name = next((n for n in z.getnames() if n.lower().endswith(".xls")), None)
            if xls_name is None:
                return None
            with tempfile.TemporaryDirectory() as tmp_dir:
                z.extract(path=tmp_dir, targets=[xls_name])
                data = (Path(tmp_dir) / xls_name).read_bytes()
        tmp_write = target_dir / f".BPR_BIA-{ts}.{uuid.uuid4().hex}.tmp"
        try:
            tmp_write.write_bytes(data)
            os.replace(tmp_write, target_path)
        finally:
            tmp_write.unlink(missing_ok=True)
        return target_path, True
    except OSError:
        return None


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


def _read_raw_xls(path: Path) -> pd.DataFrame:
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


def load_raw(path) -> pd.DataFrame:
    """Dispatcher: kalau `path` arsip .7z (dari Google Drive), ekstrak dulu ke
    folder temp lalu baca -- tiap arsip cuma isi SATU file .xls (dicek
    langsung), jadi aman diasumsikan begitu. File .xls biasa (arsip lokal
    D:\\...\\Kirim\\) dibaca langsung."""
    path = Path(path)
    if path.suffix != ".7z":
        return _read_raw_xls(path)

    with py7zr.SevenZipFile(path, mode="r") as z:
        xls_name = next((n for n in z.getnames() if n.lower().endswith(".xls")), None)
        if xls_name is None:
            raise ValueError(f"Tidak ada file .xls di dalam arsip {path.name}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            z.extract(path=tmp_dir, targets=[xls_name])
            return _read_raw_xls(Path(tmp_dir) / xls_name)


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


_MONTH_ABBR_ID = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Ags", "Sep", "Okt", "Nov", "Des"]


def previous_total_label(prev_path: Path) -> str:
    """'BPR_BIA-20260824070100.7z' (atau '.xls') -> 'TOTAL 24 Ags 2026' --
    label kolom perbandingan, gantiin label statis template asli yang sering
    telat (lihat find_previous_raw())."""
    m = _TS_RE.search(prev_path.name)
    ts = m.group(1)
    y, mo, d = int(ts[:4]), int(ts[4:6]), int(ts[6:8])
    return f"TOTAL {d} {_MONTH_ABBR_ID[mo]} {y}"


def add_previous_total(df: pd.DataFrame, id_cols: list[str], prev_df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Sisipkan kolom TOTAL hari sebelumnya tepat SETELAH kolom TOTAL yang ada
    (posisi sama seperti template asli: TOTAL | TOTAL <tgl lalu> | ACTUAL
    ORDER | %) -- gabung by id_cols (Wilayah[,Depo]), bukan by posisi baris,
    supaya tetap benar walau urutan berubah."""
    merged = df.merge(prev_df[id_cols + ["TOTAL"]].rename(columns={"TOTAL": label}), on=id_cols, how="left")
    cols = list(merged.columns)
    cols.remove(label)
    insert_at = cols.index("TOTAL") + 1
    cols = cols[:insert_at] + [label] + cols[insert_at:]
    return merged[cols]
