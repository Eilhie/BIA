"""
DAILY REPORT SETUP
Logika inti (tanpa Streamlit) buat otomatisasi rutinitas harian BIA -- salin
semua file dari folder root D:\\Data BIA\\2026\\Daily Report ke folder
tanggal HARI INI di Kirim\\{Bulan} - {MM}\\{Tanggal} {Bulan}\\.

Dipisah dari pages/16_Setup_Daily_Report.py (yang dulu isinya sendiri
semua) supaya bisa dipakai ULANG oleh modal notifikasi di app.py (muncul
di SEMUA halaman buat user Admin) tanpa duplikasi logika -- satu tempat,
dua pemanggil.

Dianalisis dulu lewat data nyata bulan September sebelum dibuat: dari 13
folder hari kerja, cuma 7 yang cocok persis dengan daftar 25 file yang
seharusnya (2 hari terlewat SAMA SEKALI, beberapa hari kekurangan/kelebihan
file, ada 1 typo nyata di nama file PDF tambahan) -- proses manual ini
genuinely tidak konsisten, itu alasan riil kenapa ini dibikin.
"""

import shutil
from datetime import datetime
from pathlib import Path

import paths

ROOT_DIR = paths.DAILY_REPORT_DIR
KIRIM_DIR = ROOT_DIR / "Kirim"

# Singkatan bulan Inggris 3-huruf -- SAMA PERSIS dengan yang sudah dipakai
# nyata di folder existing (Jan, Feb, Apr, Jul, Aug, Sep dikonfirmasi
# langsung dari isi folder -- bukan ditebak, cuma bulan yang belum pernah
# terjadi tahun ini yang diasumsikan ikut pola yang sama).
_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def today_target_folder(today: datetime | None = None) -> Path:
    """Kirim/{Bulan} - {MM}/{Tanggal} {Bulan}/ -- pola bulan Agustus/September
    (aktif saat ini): TANPA tahun, TANPA nol di depan tanggal (mis. '1 Sep',
    bukan '01 Sep 2026') -- beda dari konvensi April yang lebih lama (nama
    bulan penuh + tahun). Dipilih konvensi yang lebih baru karena itu yang
    aktif dipakai sekarang."""
    today = today or datetime.now()
    mon = _MONTH_ABBR[today.month - 1]
    month_folder = f"{mon} - {today.month:02d}"
    day_folder = f"{today.day} {mon}"
    return KIRIM_DIR / month_folder / day_folder


def root_files() -> list[Path]:
    """Semua FILE langsung di root (bukan subfolder -- itu 'Kirim' & 'back up
    rumus' sendiri, jangan ikut disalin)."""
    if not ROOT_DIR.exists():
        return []
    return [p for p in ROOT_DIR.iterdir() if p.is_file()]


def check_status(today: datetime | None = None) -> dict:
    """Baca-saja -- TIDAK membuat folder atau menyalin apa pun, aman dipanggil
    dari mana saja (mis. modal notifikasi) tiap rerun tanpa efek samping."""
    target = today_target_folder(today)
    files = root_files()
    existing_names = {p.name for p in target.iterdir() if p.is_file()} if target.exists() else set()
    missing = [f.name for f in files if f.name not in existing_names]
    return {
        "target": target,
        "total": len(files),
        "missing_count": len(missing),
        "missing_names": missing,
        "folder_exists": target.exists(),
    }


def run_setup(today: datetime | None = None) -> dict:
    """Buat folder (kalau belum ada) & salin file yang BELUM ada di sana --
    idempotent, tidak pernah menimpa file yang sudah tersalin."""
    target = today_target_folder(today)
    files = root_files()
    target.mkdir(parents=True, exist_ok=True)

    copied, skipped, failed = [], [], []
    for f in files:
        dest = target / f.name
        if dest.exists():
            skipped.append(f.name)
            continue
        try:
            shutil.copy2(f, dest)
            copied.append(f.name)
        except Exception as e:
            failed.append((f.name, str(e)))

    return {"target": target, "copied": copied, "skipped": skipped, "failed": failed}
