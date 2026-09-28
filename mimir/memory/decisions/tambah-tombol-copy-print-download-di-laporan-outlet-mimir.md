---
name: tambah-tombol-copy-print-download-di-laporan-outlet-mimir
type: decision
tags:
- mimir
- tools
- ui
- copy-print
date: '2026-09-28'
---

cari_outlet() sekarang juga menghasilkan PNG laporan (lewat render_outlet_report() di core/render_outlet_image.py, dipanggil dengan precomputed=(row_cells, info, cutoff) yang sama dipakai buat tabel HTML -- jadi data OMSHAR tidak di-query ulang). app.py menampilkan tombol Copy to Clipboard, Print, dan Download Gambar di bawah tabel, persis kode JS yang sudah dipakai halaman Omset Seeker asli (bukan ditulis ulang dari nol).

**Kenapa:** user minta fitur ini setelah lihat tabel HTML sudah bagus tapi belum ada cara mudah menyalin/mencetaknya, sama seperti yang sudah ada di Heimdall.

**Cara menerapkan:** kode JS Omset Seeker itu sudah pernah didebug nyata (clipboard API diblokir di luar secure context/LAN, window.open() diblokir popup-blocker dari dalam iframe) -- jangan tulis ulang dari nol, salin persis lalu adaptasi nama variabel. st.components.v1.html() SUDAH DEPRECATED di versi Streamlit ini (akan dihapus) -- pakai st.iframe(html_string) sebagai gantinya, otomatis mendukung string HTML mentah dan auto-size height.
