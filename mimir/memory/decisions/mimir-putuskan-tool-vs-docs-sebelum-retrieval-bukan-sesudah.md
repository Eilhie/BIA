---
name: mimir-putuskan-tool-vs-docs-sebelum-retrieval-bukan-sesudah
type: decision
tags:
- mimir
- tools
- routing
- arsitektur
date: '2026-09-28'
---

Chat Mimir sekarang memutuskan tool-vs-dokumentasi SEBELUM retrieval dijalankan, bukan sesudahnya -- perbaikan struktural, bukan tambahan aturan prompt lagi.

**Kenapa:** patch sebelumnya (aturan eksplisit soal gabungan di system prompt) cuma menang untuk SATU frasa uji ("shao kao gabungan"). Begitu user menambah kata "horeka" ("shao kao gabungan horeka"), retrieval menarik dokumen berbeda lagi (halaman Atur Gabungan HOREKA), dan pola gagal yang sama muncul lagi -- kali ini lebih parah, Mimir mengarang path palsu (menggabung dua path ASLI tapi tidak berelasi jadi satu path fiktif) dan site number fiktif. Menambal per-frasa tidak akan pernah selesai karena akan selalu ada frasa baru yang menarik dokumen relevan lain.

**Perbaikannya:** app.py sekarang dua fase. Fase 1 -- kirim pertanyaan + riwayat ke model dengan daftar tool ditawarkan, TANPA dokumentasi apa pun dilampirkan. Kalau model manggil tool, itu jalur jawabannya -- dokumentasi tidak pernah masuk sama sekali. Fase 2 -- HANYA kalau model tidak manggil tool sama sekali, baru retrieval dijalankan dan dijawab dari situ, tanpa tool ditawarkan di giliran itu. Dokumentasi dan tool tidak pernah ada di depan model dalam giliran yang sama.

**Cara menerapkan:** kalau nanti ketemu kelas kegagalan baru yang mirip (dokumentasi yang relevan/detail "menang" atas instruksi lain), jangan langsung tambah satu aturan spesifik lagi di prompt -- pertimbangkan dulu apakah ini gejala dari masalah struktural yang sama (dua sinyal bersaing di satu giliran), bukan cuma kurang satu kalimat instruksi.

**Verifikasi:** skenario gagal asli ("shao kao gabungan horeka") diuji 3x setelah fix -- 3/3 sekarang benar (sebelumnya 0/3, mengarang prosedur manual + path palsu). Regresi dicek: gabungan asli (SANUSI GABUNGAN) tetap benar, lookup biasa tetap benar, pertanyaan dokumentasi murni tetap tidak memanggil tool, outlet tidak ada tetap jujur bilang tidak ketemu, riwayat multi-giliran tetap jalan.
