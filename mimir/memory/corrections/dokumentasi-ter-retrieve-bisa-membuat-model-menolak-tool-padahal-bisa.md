---
name: dokumentasi-ter-retrieve-bisa-membuat-model-menolak-tool-padahal-bisa
type: correction
tags:
- mimir
- tools
- gabungan
- routing
- retrieval
date: '2026-09-28'
---

Mimir menolak total saat user minta omset outlet gabungan ("shao kao gabungan"), bilang datanya "cuma tersedia di file Excel eksternal, Anda tidak punya akses" -- lalu menyuruh user buka file manual. Padahal cari_nama_outlet/cari_outlet SUDAH mendukung outlet gabungan sepenuhnya (build_outlet_index() menyisipkan kode gabungan, seek_outlet() otomatis menjumlahkan toko anggota) -- dibuktikan lewat SANUSI GABUNGAN yang berhasil di-query normal.

**Kenapa terjadi:** README/docstring Heimdall punya penjelasan detail soal gabungan bersumber dari file Excel eksternal (benar, itu menjelaskan DARI MANA Heimdall dapat datanya) -- begitu pertanyaan user mengandung kata "gabungan", retrieval menarik dokumentasi itu dengan kuat, dan model memilih menjawab dari dokumentasi ("cara kerja sistem") padahal ini seharusnya permintaan DATA yang harus lewat tool. Sama seperti pola gagal sebelumnya (Hermes menjelaskan tool bukan memanggilnya) tapi kali ini dipicu oleh konten dokumentasi yang relevan justru menyesatkan, bukan oleh ketiadaan aturan.

**Cara menerapkan:** kalau nanti ada kelas pertanyaan lain yang salah dijawab pakai dokumentasi padahal harusnya tool (dokumentasinya sendiri benar, tapi memicu keputusan routing salah), tambahkan aturan EKSPLISIT di system prompt yang menyebut kasus itu by name -- seperti yang dilakukan untuk gabungan -- daripada berharap aturan umum "kalau minta data panggil tool" cukup kuat melawan dokumentasi yang sangat relevan/detail.

**Catatan sisa (belum diperbaiki):** setelah fix, model kadang menyebut outlet biasa (bukan gabungan asli, tidak ada tag "(Gabungan)") sebagai "gabungan" hanya karena user pakai kata itu, dan sempat menjumlahkan dua brand berbeda jadi "total gabungan" yang tidak diminta -- angka masing-masing tetap benar/dari tool, tapi narasinya melebih-lebihkan. Belum diperbaiki, perlu diskusi apakah worth effort-nya.
