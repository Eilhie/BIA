# OT AUTOMATION

Pipeline untuk mengolah data OMSHAR dari server menjadi CSV query-ready dan laporan PNG per outlet.

---

## Struktur Folder

```
D:\SDAAREA\
├── AMBIL DATA BARU.bat          ← Entry point utama (sync + transpose)
├── AMBIL DATA BARU TEST.bat     ← Versi test (semua output ke test\)
├── SYNC OMSHAR FAST.bat         ← Sync OMSHAR saja (tanpa transpose)
├── README.md                    ← File ini
│
├── DB\                          ← XLS OMSHAR hasil sync dari server
├── sync_log.txt                 ← Log setiap sesi sync
├── SKU_Terlewat.txt             ← SKU tidak ditemukan di server (jika ada)
│
├── omset_seeker.py              ← Query data outlet dari CSV
├── render_outlet_image.py       ← Generate PNG laporan OMSET OUTLET
├── omset_search_app.py          ← Halaman utama web app (Streamlit) — Cari Outlet
├── CARI OUTLET.bat              ← Buka web app di browser (localhost saja)
├── pages\
│   └── 1_Sync_dan_Transpose.py  ← Halaman Sync + Transpose di web app yang sama
│
└── omset_pipeline\
    ├── transpose.py             ← Konversi XLS → XLSX + CSV
    ├── RUN.bat                  ← Shortcut transpose manual
    └── output\
        ├── DB TRANSPOSED\UMUM\  ← XLSX per brand UMUM (untuk atasan)
        ├── DB TRANSPOSED\HOREKA\← XLSX per brand HOREKA (untuk atasan)
        ├── CSV\UMUM\            ← CSV query UMUM (input omset_seeker)
        ├── CSV\HOREKA\          ← CSV query HOREKA (input omset_seeker)
        └── IMAGE\               ← PNG laporan per outlet
```

**Terpisah dari pipeline ini:**
- `D:\EAO\sync_eao.bat` — sync file EAO (Daily/Monthly) dari server
- `D:\DB OMSHAR\SKU_LIST\` — daftar SKU yang disync (config, jangan diubah sembarangan)

---

## Prasyarat

Python 3.x dengan library berikut:
```
pip install xlrd openpyxl pandas matplotlib
```

Akses jaringan ke `\\10.4.1.25\Bev\OMSHAR`

---

## Alur Kerja

### 1. Ambil Data Baru (rutin setelah OMSHAR diupdate di server)

**Cara termudah (tanpa command line):** double-click **`CARI OUTLET.bat`**,
lalu buka halaman **"Sync dan Transpose"** di sidebar. Centang UMUM/HOREKA,
klik Mulai Sync (sync ke `D:\DB OMSHAR\DB`, bukan `D:\SDAAREA\DB`), lalu
pilih mode transpose dan klik Mulai Transpose — log berjalan live di layar,
tidak perlu buka Command Prompt sama sekali.

**Lewat command line/.bat lama** (kalau perlu): double-click **`AMBIL DATA BARU.bat`**

Script ini menjalankan dua langkah:

**Step 1 — Sync OMSHAR**
- Membaca daftar SKU dari `D:\DB OMSHAR\SKU_LIST\UMUM\` dan `HOREKA\`
- Mengunduh/memperbarui file XLS dari `\\10.4.1.25\Bev\OMSHAR` ke `D:\SDAAREA\DB\`
- Menggunakan robocopy `/MT:8 /XO` — paralel 8 thread, skip file yang sudah up-to-date
- Setelah sync, menampilkan ringkasan: ada SKU terlewat? File terbaru tanggal berapa?

**Step 2 — Transpose**
- Pilih mode: `[1] UMUM`, `[2] HOREKA`, `[3] SEMUA`, `[4] Lewati`
- Membuka XLS per brand dari `DB\`, menggabungkan sheet wilayah
  - UMUM: BTN DKI BDB JBU JBS JTU JTS JIU JIS BLI → **DAPUL**
  - UMUM: SMU SMB SMS LPB NTR KLT KLB SLS SLU PPA → **LAPUL**
  - HOREKA: 19 wilayah (DAPUL + LAPUL kecuali PPA) → **HOREKA**
- Menyimpan XLSX (untuk atasan) + CSV query (untuk Python) per brand
- Berjalan paralel 4 proses — output di terminal mungkin bercampur urutan

> Indikator data terkini: lihat tanggal **CUT OFF** saat query omset_seeker,
> bukan tanggal file di folder.

---

### 2. Query Data Outlet

**Cara termudah (tanpa command line):** double-click **`CARI OUTLET.bat`**.
Membuka web app di browser (`http://localhost:8501`, hanya bisa diakses dari
komputer ini sendiri, tidak ter-expose ke jaringan/internet). Isi Site
number, pilih grup, klik Cari — tabel muncul, ada tombol untuk generate &
download PNG laporan. Centang "With Keg" untuk outlet HOREKA yang jual
bir keg/draft.

**Lewat command line** (kalau perlu):
```
cd D:\SDAAREA
python omset_seeker.py
```

Masukkan **Site number** (contoh: `0815-02000166`) dan grup (`UMUM` atau `HOREKA`).
Menampilkan tabel KRT per brand per bulan + validasi terhadap total BIR.

---

### 3. Generate PNG Laporan

```
cd D:\SDAAREA
python render_outlet_image.py
```

Output disimpan di `omset_pipeline\output\IMAGE\`.

---

### 4. Transpose Manual (tanpa sync)

Double-click **`omset_pipeline\RUN.bat`** — pilih mode transpose.

---

### 5. Sync EAO

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

21 brand di transpose (19 SKU + BIR + DIV AB1):

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

Brand dengan >1 file: di-stack langsung (bukan di-merge saat transpose).
Penjumlahan per outlet dilakukan di `omset_seeker.py` saat query.

---

## Catatan Teknis

- **BEV** tidak punya file sendiri — dihitung otomatis: `DIV AB1 − BIR` per bulan
- CSV suffix `_query.csv` sudah tanpa 8 baris header, digunakan Python
- CSV suffix tanpa `_query` menyertakan header, untuk dibuka di Excel
- `transpose.py` mendukung override path via env var:
  - `OMSHAR_DIR` — sumber XLS (default: `D:\SDAAREA\DB`)
  - `TRANSPOSE_OUT` — output XLSX (default: `omset_pipeline\output\DB TRANSPOSED`)
  - `TRANSPOSE_CSV` — output CSV (default: `omset_pipeline\output\CSV`)
