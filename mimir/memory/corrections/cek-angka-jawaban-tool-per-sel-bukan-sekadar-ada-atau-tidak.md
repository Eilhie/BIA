---
name: cek-angka-jawaban-tool-per-sel-bukan-sekadar-ada-atau-tidak
type: correction
tags:
- mimir
- tool
- pengujian
- halusinasi
date: '2026-09-21'
---

Saat memeriksa apakah jawaban LLM benar-benar berdasarkan hasil tool, mengecek bahwa setiap angka di jawaban ADA di output tool itu tidak cukup -- pengecekan seperti itu lolos padahal kedua model memberi jawaban yang salah.

**Yang terjadi:** pada pertanyaan lanjutan (bulan terakhir, nilai per brand), Hermes menyebut bulan yang salah dan Qwen menempelkan angka asli dari sel lain ke brand yang salah (SIDU 15.0 padahal nilai sebenarnya 0.0). Semua angka memang ada di tabel; hanya salah brand/bulan.

**Cara menerapkan:** (1) uji terhadap kebenaran dasar yang diambil dari tool itu sendiri, bukan cuma keberadaan angka; (2) suruh tool menghitung sendiri pertanyaan yang jelas akan ditanyakan (bulan terakhir + nilai per brand, ditulis brand=nilai) supaya model tinggal menyampaikan, bukan membaca tabel lebar; (3) suruh model memanggil tool lagi untuk pertanyaan lanjutan tentang angka, bukan membaca angka lama dari riwayat chat.
