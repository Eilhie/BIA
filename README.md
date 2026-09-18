# SDA Automation

Repo ini berisi dua project terpisah:

- **[`heimdall/`](heimdall/README.md)** (codename Heimdall) — aplikasi web (Streamlit, multi-halaman) untuk mengolah data OMSHAR dari server jadi CSV query-ready + laporan PNG per outlet, plus sejumlah halaman pendukung lain (klaim SKU, gabungan toko, cukai kompetitor, BPR, dsb). Ini yang dijelaskan sisa dokumen ini.
- **[`mimir/`](mimir/README.md)** (codename Mimir) — Wiki LLM lokal (tanya-jawab tentang cara kerja sistem ini, jawaban diambil dari dokumentasi asli, bukan dikarang).

Dulu Heimdall adalah kumpulan `.bat` + script command-line yang berdiri sendiri di root repo; sekarang semuanya lewat satu web app, dibuka lewat **`BIFROST.bat`** (menu buat pilih Heimdall/Heimdall LAN/Heimdall DEV/Mimir). `.bat` yang masih relevan di luar itu: `AMBIL DATA BARU TEST.bat` (sync ke folder test, tidak menyentuh data produksi) dan `BUKA OMSHAR.bat` (buka file `.xls` mentah langsung per SKU, tanpa lewat web app).

---

## Struktur Folder

```
D:\SDAAREA\
├── BIFROST.bat                  ← Satu-satunya launcher: pilih Heimdall/Heimdall LAN/Heimdall DEV/Mimir
├── AMBIL DATA BARU TEST.bat     ← Sync + transpose ke test\ (tidak menyentuh DB produksi)
├── BUKA OMSHAR.bat              ← Buka file .xls mentah langsung per SKU (manual)
├── README.md                    ← File ini
│
├── heimdall\                    ← Codename Heimdall -- app OMSHAR/EAO, lihat heimdall/README.md
│   ├── app.py                       ← Entry point web app -- daftar & urutan semua halaman
│   ├── config\config.yaml           ← Level akses per halaman
│   ├── core\                        ← auth, database, paths, omset_seeker, render_outlet_image (dipakai semua domain)
│   ├── omset_search_app.py          ← Halaman utama web app — Cari Outlet (Omset Seeker)
│   ├── omset_pipeline\              ← transpose.py, gabungan_live_generator.py, sql_cache.py
│   │   └── output\
│   │       ├── DB TRANSPOSED\UMUM\      ← XLSX per brand UMUM (untuk atasan)
│   │       ├── DB TRANSPOSED\HOREKA\    ← XLSX per brand HOREKA (untuk atasan)
│   │       ├── CSV\UMUM\                ← CSV query UMUM (input omset_seeker)
│   │       ├── CSV\HOREKA\              ← CSV query HOREKA (input omset_seeker)
│   │       └── CSV\{UMUM,HOREKA}\SKU_RAW\ ← Cache cepat per SKU individual (fallback: baca .xls mentah, ~20-25 detik/SKU)
│   ├── mclub\, cukai\, daily_report\, bpr\, eao\, sku\, sync\, admin\
│   │                                 ← Satu folder per domain (pipeline + halaman terkait), lihat README masing-masing
│   └── DB\auth\access_log.db        ← SQLite: akun, sesi, audit trail (gitignored)
│
└── mimir\                       ← Codename Mimir -- Wiki LLM lokal, lihat mimir/README.md
    ├── app.py                       ← Chat UI (Streamlit, port 8600)
    ├── indexer.py                   ← Bangun index dari README + docstring
    └── .index\                      ← Vector DB Chroma (gitignored)
```

Setiap folder domain di dalam `heimdall\` (`core`, `mclub`, `cukai`, `daily_report`, `bpr`, `eao`, `sku`, `sync`, `admin`, `omset_pipeline`) punya `README.md` sendiri yang menjelaskan isinya lebih detail -- lihat [`heimdall/README.md`](heimdall/README.md) untuk daftar lengkap.

**Data mentah & config, di luar folder ini:**
- `D:\DB OMSHAR\DB\` — XLS OMSHAR hasil sync dari server (bukan `D:\SDAAREA\DB`, itu default kosong)
- `D:\DB OMSHAR\SKU_LIST\{UMUM,HOREKA}\*.txt` — daftar SKU yang disync (edit lewat halaman **Atur SKU Sync**)
- `D:\Data BIA\INFO BIA\Toko Gabungan\` — file Excel gabungan toko (UMUM & HOREKA), dari divisi lain, read-only
- `D:\cukai kompetitor\` — file Excel kerja analis, read-only
- `D:\EAO\sync_eao.bat` — sync file EAO (Daily/Monthly) dari server, independen dari pipeline ini

---

## Prasyarat

Python 3.x dengan dependency di `heimdall/requirements.txt` (`streamlit`, `pandas`,
`openpyxl`, `xlrd`, `matplotlib`, `bcrypt`, `extra-streamlit-components`,
`PyYAML`, `py7zr`):
```
pip install -r heimdall/requirements.txt
```

Akses jaringan ke `\\10.4.1.25\Bev\OMSHAR`

---

## Alur Kerja

### 1. Ambil Data Baru (rutin setelah OMSHAR diupdate di server)

Double-click **`BIFROST.bat`**, pilih **Heimdall**, lalu buka halaman
**"Sync dan Transpose"** di sidebar. Centang UMUM/HOREKA, klik Mulai Sync
(sync ke `D:\DB OMSHAR\DB`, bukan `D:\SDAAREA\DB`), lalu pilih mode
transpose dan klik Mulai Transpose — log berjalan live di layar, tidak
perlu buka Command Prompt sama sekali. Ini satu-satunya cara resmi
sekarang -- lihat [`heimdall/sync/README.md`](heimdall/sync/README.md).

**Step 1 — Sync OMSHAR**
- Membaca daftar SKU dari `D:\DB OMSHAR\SKU_LIST\UMUM\` dan `HOREKA\`
- Mengunduh/memperbarui file XLS dari `\\10.4.1.25\Bev\OMSHAR` ke `D:\DB OMSHAR\DB\`
- Robocopy `/MT:8 /XO /R:1 /W:1` per grup SKU_LIST — paralel 8 thread, skip file yang sudah up-to-date
- Exit code robocopy DICEK per batch (bukan cuma `file.exists()`) -- kalau robocopy
  melapor gagal menyalin sebagian file, itu ditampilkan terpisah sebagai
  peringatan (file lama BISA JADI masih tertinggal), bukan diam-diam dianggap sukses
- Setelah sync, menampilkan ringkasan: ada SKU terlewat? Ada batch yang gagal ditarik?

**Step 2 — Transpose** (`omset_pipeline/transpose.py`, 4 mode CLI: `umum` / `horeka` / `horeka_keg` / `all`)
- UI web punya 4 pilihan: **UMUM**, **HOREKA** (brand dasar saja), **HOREKA + KEG/PET**
  (tambah ~15 brand draft/keg/PET), **ALL** (semuanya)
- Membuka XLS per brand dari `DB\`, menggabungkan sheet wilayah
  - UMUM: BTN DKI BDB JBU JBS JTU JTS JIU JIS BLI → **DAPUL**
  - UMUM: SMU SMB SMS LPB NTR KLT KLB SLS SLU PPA → **LAPUL**
  - HOREKA: 19 wilayah (DAPUL + LAPUL kecuali PPA) → **HOREKA**
- Menyimpan XLSX (untuk atasan) + CSV query (untuk Python) per brand, plus cache
  `SKU_RAW` per file mentah yang dibaca (dipakai jalur cepat Cek Klaim SKU / Detail SKU Brand Besar)
- Berjalan paralel di `multiprocessing.Pool`, sampai 20 proses (dibatasi jumlah core
  CPU & jumlah brand di batch itu) — output terminal antar-brand bisa bercampur urutan
- **Transpose SKU individual (custom)**: expander terpisah di halaman yang sama --
  pilih SKU manapun (dari 230 kode di SKU_LIST, bukan cuma 59 brand rollup resmi)
  buat di-cache duluan tanpa menyentuh brand rollup resmi apa pun. Cocok buat SKU
  yang baru dicek di Detail SKU Brand Besar dan mau dipercepat untuk kunjungan berikutnya.

> Indikator data terkini: lihat tanggal **CUT OFF** saat query omset_seeker --
> ditampilkan **per brand**, bukan satu tanggal untuk seluruh outlet, karena
> brand yang beda bisa punya tanggal sync terakhir yang beda juga (lihat
> halaman **Cek Cutoff OMSHAR**). Ini bukan bug -- cutoff diambil langsung
> dari isi file mentah tiap brand, bukan tanggal file di folder.

---

### 2. Query Data Outlet

Double-click **`BIFROST.bat`**, pilih **Heimdall**. Membuka web app di
browser (`http://localhost:8501`, hanya bisa diakses dari komputer ini
sendiri, tidak ter-expose ke jaringan/internet). Isi Site number, pilih
grup, klik Cari — tabel muncul, ada tombol untuk generate & download PNG
laporan. Centang "Tampilkan KEG/PET (HOREKA)" di sidebar untuk memunculkan
breakdown brand draft/keg/PET tambahan pada outlet HOREKA.

---

### 3. Sync EAO

Double-click **`D:\EAO\sync_eao.bat`**

Berbeda dari pipeline OMSHAR. Mengunduh file EAO Daily/Monthly/P90 dari
`\\10.4.1.25\Bev\EAO\{TAHUN}\{BULAN}\` ke `D:\EAO\`.

---

## Mode Test

Double-click **`AMBIL DATA BARU TEST.bat`**

Semua output diarahkan ke `D:\SDAAREA\test\` — tidak menyentuh `DB\` produksi.
Gunakan ini untuk verifikasi sebelum commit ke data nyata.

---

## Konfigurasi SKU

Daftar SKU yang disync ada di `D:\DB OMSHAR\SKU_LIST\`:
```
SKU_LIST\
├── UMUM\
│   ├── ABIDIN.txt
│   ├── BIR&AB1.txt      ← berisi: BIR, DIV-AB1, BIR-MIX
│   └── ...
└── HOREKA\
    ├── ABIDIN.txt
    └── ...
```

Setiap file `.txt` berisi satu nama SKU per baris (tanpa prefix `OMSHAR UMUM`).
Contoh isi `BIR&AB1.txt`:
```
BIR
DIV-AB1
BIR-MIX
```

Untuk menambah SKU baru: tambahkan baris di file `.txt` yang sesuai,
lalu jalankan sync berikutnya.

---

## Brand Mapping

22 brand rollup resmi di transpose (20 SKU + BIR + DIV AB1) -- `BRAND_ORDER` di
`transpose.py`/`omset_seeker.py`, isinya harus sama persis di kedua file:

| Brand | File UMUM | File HOREKA |
|---|---|---|
| ABIDIN | ABIDIN | ABIDIN |
| AMERAJA | AMERAJA | AMERAJA |
| APIDIN | APIDIN | APIDIN |
| SOMAEK | GBSM | BSM |
| SIMER | SINGARAJA AMER BREMER + CAN | sama |
| SIJO | SINGARAJA AHI BREMER + CAN | sama |
| SIDU | SINGARAJA ARAK JERUK MADU | SAJMP330 |
| SIRAK | SINGARAJA ARAK BREMER | sama |
| SPA FILTERED | SPAFC320 + SPAFP250 | sama |
| SPA UNFILTERED | SPAUC320 + SPAUP250 | sama |
| SINGARAJA | SINGARAJA | sama |
| PROST PILSENER | PPIL | sama |
| PROST LAGER | PLAG | sama |
| PRL LAGER | PRL | sama |
| PRL APPLE LIME | RFALP330 + RFALC320 | RFALP330 + RFALC330 |
| PRL RASPBERRY | RFRBP330 + RPAUC320 | RFRBP320 + RPAUC320 |
| PROST ALSTER | PALS | sama |
| KALTENBERG | KRL | sama |
| KONIG WEISSBIER | WBR | sama |
| KONIG DUNKEL | KLW640DK + KLW330DK | sama |
| BIR | BIR | sama |
| DIV AB1 | DIV-AB1 | sama |

"PRL" (PRL LAGER/APPLE LIME/RASPBERRY) = singkatan "Prost Rajawali" -- tiga
varian rasa dalam satu keluarga produk, bukan brand terpisah dari "PROST
RAJAWALI"; `SINGARAJA BREMER HWG` bukan brand rollup tersendiri, lihat tabel
KEG/PET di bawah.

Brand dengan >1 file: di-stack langsung (bukan di-merge saat transpose).
Penjumlahan per outlet dilakukan di `omset_seeker.py` saat query.

### Brand KEG/PET tambahan (HOREKA-only)

15 brand tambahan, HOREKA saja, TIDAK ikut di `BRAND_ORDER` -- cuma muncul
kalau dipilih lewat mode Transpose **"HOREKA + KEG/PET"** dan/atau centang
**"Tampilkan KEG/PET (HOREKA)"** di Omset Seeker. `HOREKA_KEG_BRAND_ORDER` /
`HOREKA_KEG_FILE` di `transpose.py`:

| Brand | File |
|---|---|
| SINGARAJA KEG 10/20/30 | SKEG10P / SKEG20P / SKEG30P |
| SINGARAJA BREMER HWG | SKB620PH |
| PROST PILSENER KEG 10/20/30 | PKEG10P / PKEG20P / PKEG30P |
| PROST LAGER KEG 10/20/30 | PKEG10L / PKEG20L / PKEG30L |
| PROST RAJAWALI KEG 10/30 | RPKEG10L / RPKEG30L |
| SINGARAJA PET 20L | SPET20P |
| PROST PILSENER PET 20L | PPET20P |
| PROST LAGER PET 20L | PPET20L |
| PROST RAJAWALI PET 20L | RPPET20L |

Beberapa kode di sini (KEG10, PET20L, HWG) ditambahkan sebagai fallback siap
pakai sebelum SKU-nya benar-benar disync -- `process_brand()` otomatis
`[SKIP]` (bukan gagal) kalau file sumbernya belum ada.

---

## Catatan Teknis

- **BEV** tidak punya file sendiri — dihitung otomatis: `DIV AB1 − BIR` per bulan
- CSV suffix `_query.csv` sudah tanpa 8 baris header, digunakan Python
- CSV suffix tanpa `_query` menyertakan header, untuk dibuka di Excel
- `transpose.py` mendukung override path via env var:
  - `OMSHAR_DIR` — sumber XLS (default: `D:\SDAAREA\DB`, di web app di-set ke `D:\DB OMSHAR\DB` lewat `heimdall/sync/1_Sync_dan_Transpose.py`)
  - `TRANSPOSE_OUT` — output XLSX (default: `omset_pipeline\output\DB TRANSPOSED`)
  - `TRANSPOSE_CSV` — output CSV (default: `omset_pipeline\output\CSV`)
- **`paths.py`** — satu sumber kebenaran untuk semua path data eksternal (di luar
  `D:\SDAAREA`, sebelumnya di-hardcode berulang di banyak file). Semua override-able
  via env var (default-nya path yang sudah dipakai di PC ini, jadi clone ke laptop
  lain tinggal set env var yang beda, tanpa ubah kode):
  - `SDA_OMSHAR_DB_DIR` (default `D:\DB OMSHAR\DB`), `SDA_SKU_LIST_DIR` (default `D:\DB OMSHAR\SKU_LIST`)
  - `SDA_DAILY_REPORT_DIR` (default `D:\Data BIA\2026\Daily Report`), `SDA_GDRIVE_BPR_DIR` (default `G:\My Drive\BPR BIA`)
  - `SDA_CUKAI_DIR`, `SDA_EAO_DIR`, `SDA_MCLUB_DIR`, `SDA_TOKO_GABUNGAN_DIR`
  - Path jaringan (`\\10.4.1.25\...`) sengaja TIDAK di sini -- itu alamat server
    yang sama dari komputer mana pun, bukan struktur drive lokal per PC.
  - `omset_pipeline/sql_cache.py` (prototipe, belum dipakai halaman manapun)
    sengaja belum ikut di-refactor -- lihat komentar "THIS FILE IS A PROTOTYPE" di file itu.
- **Toko Gabungan** (kode outlet gabungan, lihat halaman Gabungan UMUM/HOREKA):
  dibaca dari file Excel eksternal di `D:\Data BIA\INFO BIA\Toko Gabungan\`,
  murni read-only -- editing dilakukan di file itu sendiri, bukan lewat app ini.
  UMUM: file `Toko Gabungan Update <tgl> <bulan> <tahun>.xlsx` ATAU
  `Toko Gabungan (Formula Live) - Data <bulan> <tahun>.xlsx`, mana pun lebih
  baru. HOREKA: file terpisah `Gabungan HOREKA Update <tgl> <bulan> <tahun>.xlsx`.
- **Level akses** (0-5) diatur per halaman di `config/config.yaml` (`pages:`)
  dan ditegakkan lewat `auth.require_level()` di tiap halaman; login/akun
  dikelola di halaman **Kelola User**, log akses di **Audit Trail**.
