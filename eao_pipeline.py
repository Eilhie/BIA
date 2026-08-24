"""
EAO PIPELINE
Monitoring + sync manual untuk data EAO (sistem sell-out terpisah dari OMSHAR) --
sumbernya server network \\10.4.1.25\\Bev\\EAO\\{tahun}\\{bulan}\\{Daily,Monthly},
disinkronkan otomatis ke D:\\EAO tiap ~10 menit lewat Windows Task Scheduler +
sync_eao.bat (robocopy). Modul ini TIDAK mengganti/menyentuh sync_eao.bat sama
sekali (task terjadwal tetap jalan independen) -- ini cuma kasih VISIBILITAS
(apa yang ada di server vs lokal, riwayat sync) + tombol sync manual dari app,
dengan logika yang meniru KEY_DAILY/KEY_MONTHLY di .bat tapi dieksekusi native
Python (bukan shell out ke .bat, karena .bat punya `pause` + popup GUI yang
bakal nge-hang kalau dipanggil headless dari Streamlit).
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

SERVER_BASE = Path(r"\\10.4.1.25\Bev\EAO")
LOCAL_DIR = Path(r"D:\EAO")
SYNC_LOG_PATH = LOCAL_DIR / "sync_log.txt"

# Sama persis dengan KEY_DAILY/KEY_MONTHLY di sync_eao.bat -- file INI yang
# ditarik otomatis oleh task terjadwal, sisanya di server TIDAK pernah ditarik
# (lihat list_server_month() untuk lihat semua yang ada di server, termasuk
# yang tidak masuk daftar ini).
KEY_PATTERNS = [
    "TOTAL NON HOREKA DAILY.xlsx", "TOTAL P90 DAILY.xlsx", "TOTAL HOREKA DAILY.xlsx",
    "TOTAL NON HOREKA MONTHLY.xlsx", "TOTAL P90 MONTHLY.xlsx", "TOTAL HOREKA MONTHLY.xlsx",
]


def is_server_reachable() -> bool:
    try:
        return SERVER_BASE.exists()
    except OSError:
        return False


def _find_month_folder(year: int, month: int) -> Path | None:
    """Cari folder bulan di server -- nama foldernya '08-Agt' dsb, casing/singkatan
    Indonesia bisa beda-beda, jadi scan prefix 2 digit bulan daripada hardcode nama."""
    year_dir = SERVER_BASE / str(year)
    if not year_dir.exists():
        return None
    prefix = f"{month:02d}-"
    for d in year_dir.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            return d
    return None


def _list_dir_files(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for f in path.iterdir():
        if f.is_file() and not f.name.startswith("~$"):
            stat = f.stat()
            out.append({"name": f.name, "size": stat.st_size, "mtime": stat.st_mtime})
    return sorted(out, key=lambda r: r["name"])


def list_server_month(year: int, month: int) -> dict:
    """Semua file di server untuk bulan itu (Daily + Monthly) -- termasuk file yang
    TIDAK ditarik otomatis oleh sync_eao.bat (mis. varian DA/SPV HOREKA, AE, EXC ALT,
    snapshot per-tanggal), supaya kelihatan apa yang sebenarnya ada di server."""
    month_dir = _find_month_folder(year, month)
    if month_dir is None:
        return {"found": False, "folder": None}
    return {
        "found": True,
        "folder": month_dir,
        "daily": _list_dir_files(month_dir / "Daily"),
        "monthly": _list_dir_files(month_dir / "Monthly"),
    }


def list_local_files() -> list[dict]:
    files = _list_dir_files(LOCAL_DIR)
    for f in files:
        f["is_key"] = any(f["name"].endswith(p) for p in KEY_PATTERNS)
    return sorted(files, key=lambda r: (-r["is_key"], r["name"]))


def read_sync_log(n: int = 30) -> list[str]:
    if not SYNC_LOG_PATH.exists():
        return []
    lines = SYNC_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:][::-1]


def sync_now(today: datetime | None = None) -> dict:
    """Tarik file KEY_PATTERNS bulan berjalan dari server ke D:\\EAO kalau versi
    server lebih baru dari lokal -- logika sama dengan robocopy /maxage /XO di
    sync_eao.bat, tapi dieksekusi native (aman dipanggil dari Streamlit, tidak
    ada `pause`/popup). TIDAK menyentuh file lain di server yang bukan KEY_PATTERNS
    -- itu scope sync_eao.bat, bukan tombol ini."""
    d = today or datetime.now()
    if not is_server_reachable():
        return {"ok": False, "error": "Server \\\\10.4.1.25\\Bev tidak terjangkau -- pastikan VPN aktif."}

    month_dir = _find_month_folder(d.year, d.month)
    if month_dir is None:
        return {"ok": False, "error": f"Folder bulan {d.year}-{d.month:02d} belum ada di server."}

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    skipped = []
    for subdir_name in ("Daily", "Monthly"):
        subdir = month_dir / subdir_name
        if not subdir.exists():
            continue
        for f in subdir.iterdir():
            if not f.is_file() or f.name.startswith("~$"):
                continue
            if not any(f.name.endswith(p) for p in KEY_PATTERNS):
                continue
            dest = LOCAL_DIR / f.name
            src_mtime = f.stat().st_mtime
            if dest.exists() and dest.stat().st_mtime >= src_mtime:
                skipped.append(f.name)
                continue
            shutil.copy2(f, dest)
            copied.append(f.name)

    log_line = (
        f"{d.strftime('%d/%m/%Y %H:%M:%S')} - Sync manual (app) selesai. "
        f"Disalin: {len(copied)}, dilewati (sudah terbaru): {len(skipped)}\n"
    )
    try:
        with open(SYNC_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except OSError:
        pass

    return {"ok": True, "copied": copied, "skipped": skipped, "month_folder": month_dir.name}
