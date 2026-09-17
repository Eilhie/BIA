"""
paths.py
Satu sumber kebenaran untuk semua path data eksternal (di luar D:\\SDAAREA)
yang dipakai app ini. Sebelumnya path yang SAMA di-hardcode ke D:\\... secara
independen di banyak file sekaligus (mis. "D:\\DB OMSHAR\\DB" didefinisikan
sendiri-sendiri di 6 file berbeda) -- risiko nyata: gampang lupa ubah semua
tempat sekaligus kalau path-nya berubah, dan menghalangi clone app ini ke
laptop lain yang drive/struktur foldernya beda.

Semua path di bawah override-able lewat environment variable, default-nya
tetap PERSIS path yang sudah dipakai sekarang di PC ini -- jadi perilaku di
PC ini tidak berubah sama sekali kalau env var tidak di-set. Clone ke laptop
lain tinggal set env var yang sesuai sebelum jalankan app, tidak perlu ubah
kode di mana pun.

Path jaringan (\\\\10.4.1.25\\...) SENGAJA tidak dimasukkan sini -- itu
alamat server perusahaan yang sama dari komputer mana pun di jaringan
kantor, bukan struktur drive lokal yang beda per PC.
"""

import os
from pathlib import Path


def _env_path(env_name: str, default: str) -> Path:
    return Path(os.environ.get(env_name, default))


# Data OMSHAR hasil sync (lihat pages/1_Sync_dan_Transpose.py) -- BUKAN
# D:\SDAAREA\DB (default nominal transpose.py itu selalu kosong, lihat
# [[feedback_data_source_location]]).
OMSHAR_DB_DIR = _env_path("SDA_OMSHAR_DB_DIR", r"D:\DB OMSHAR\DB")

# Daftar SKU yang disync, dikelola lewat halaman Atur SKU Sync.
SKU_LIST_DIR = _env_path("SDA_SKU_LIST_DIR", r"D:\DB OMSHAR\SKU_LIST")

# Root folder "Daily Report" -- dipakai BPR pipeline (fallback arsip lokal)
# + Daily Report Setup (auto-copy ke folder tanggal hari ini).
DAILY_REPORT_DIR = _env_path("SDA_DAILY_REPORT_DIR", r"D:\Data BIA\2026\Daily Report")

# Google Drive (Drive for Desktop) -- drive letter bisa beda per PC/user,
# lihat bpr_pipeline.py untuk kenapa ini sumber UTAMA BPR (bukan arsip D:
# lokal, yang cuma salinan manual seseorang dan kadang telat/skip).
GDRIVE_BPR_DIR = _env_path("SDA_GDRIVE_BPR_DIR", r"G:\My Drive\BPR BIA")

# File kerja analis Cukai Kompetitor -- read-only, milik divisi lain.
CUKAI_DIR = _env_path("SDA_CUKAI_DIR", r"D:\cukai kompetitor")

# Hasil sync EAO (sistem sell-out terpisah dari OMSHAR, lihat eao_pipeline.py).
EAO_DIR = _env_path("SDA_EAO_DIR", r"D:\EAO")

# File kerja + folder RAW Outlet MClub Platinum Gold -- milik divisi lain.
MCLUB_DIR = _env_path("SDA_MCLUB_DIR", r"D:\OUTLET MCLUB PLATINUM GOLD")

# File Excel Toko Gabungan (UMUM & HOREKA) dari divisi lain -- read-only.
TOKO_GABUNGAN_DIR = _env_path("SDA_TOKO_GABUNGAN_DIR", r"D:\Data BIA\INFO BIA\Toko Gabungan")
