"""
scheduled_sync.py
Entry point STANDALONE untuk Windows Task Scheduler -- gabungan 2 tugas
berkala dalam SATU scheduled task (bukan 2 task terpisah, cuma 1 slot yang
perlu di-maintain):

  1. Sync EAO (eao_pipeline.sync_now()) -- gantikan robocopy di
     sync_eao.bat yang lama.
  2. Backup bulanan OMSHAR90 (omshar90_pipeline.backup_monthly()) --
     idempotent, aman dipanggil tiap kali script ini jalan (cuma benar-
     benar kerja sekali per bulan, sisanya cuma cek-lalu-skip).

TIDAK ADA popup/MessageBox/`pause` sama sekali -- sync_eao.bat lama punya
keduanya (MessageBox tiap ada file baru + `pause` di ujung yang SELALU
jalan), yang kalau dijadwalkan tiap ~10 menit numpuk jadi banyak dialog/
jendela cmd yang harus ditutup manual satu-satu. Semua hasil ditulis ke
scheduled_sync_log.txt saja.

Setup Task Scheduler (GANTI action dari sync_eao.bat lama, jangan jalankan
keduanya sekaligus -- nanti EAO ke-sync 2x tiap siklus, harmless tapi
percuma):
  Program/script : <path ke pythonw.exe, BUKAN python.exe -- lihat catatan
                    di bawah kenapa harus pythonw>
  Add arguments  : "D:\\SDAAREA\\heimdall\\scheduled_sync.py"
  Start in       : D:\\SDAAREA\\heimdall
  Trigger        : sama seperti sync_eao.bat lama (tiap ~10-15 menit)

Kenapa pythonw.exe (bukan python.exe): python.exe selalu buka jendela
console biar bisa print(); pythonw.exe (satu folder yang sama dengan
python.exe di instalasi Windows manapun) jalan TANPA jendela sama sekali --
exact padanan .pyw. Cek lokasinya: sama dengan `python.exe` tapi nama file
`pythonw.exe` di folder yang sama (`where python` untuk tahu foldernya).
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LOG_PATH = Path(__file__).resolve().parent / "scheduled_sync_log.txt"


def _log(line: str) -> None:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{ts} - {line}\n")
    except OSError:
        pass


def run_eao_sync() -> None:
    """Silent kalau tidak ada perubahan (sama seperti perilaku lama) --
    cuma log kalau BENERAN ada file yang disalin atau kalau gagal, supaya
    log-nya tidak banjir baris yang sama tiap ~10 menit."""
    try:
        from eao import eao_pipeline
        result = eao_pipeline.sync_now()
        if not result["ok"]:
            _log(f"EAO sync GAGAL -- {result['error']}")
        elif result["copied"]:
            _log(f"EAO sync OK -- disalin {len(result['copied'])}: {', '.join(result['copied'])}")
    except Exception:
        _log(f"EAO sync EXCEPTION -- {traceback.format_exc(limit=3)}")


def run_omshar90_backup() -> None:
    """Silent kalau sudah ke-backup bulan ini atau arsipnya belum muncul di
    Drive (dua-duanya kondisi normal yang akan terus kejadian tiap siklus
    sampai bulan ganti / Apps Script jalan) -- cuma log kalau BENERAN
    baru selesai backup, atau kalau gagal."""
    try:
        from omshar90 import omshar90_pipeline
        result = omshar90_pipeline.backup_monthly()
        if result.get("done"):
            _log(f"OMSHAR90 backup OK -- {result['target']} ({', '.join(result['extracted'])})")
    except Exception:
        _log(f"OMSHAR90 backup EXCEPTION -- {traceback.format_exc(limit=3)}")


if __name__ == "__main__":
    run_eao_sync()
    run_omshar90_backup()
