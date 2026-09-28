---
name: ganti-model-default-mimir-ke-qwen3-8b-hapus-deepseek-r1
type: decision
tags:
- mimir
- model
- qwen3
- deepseek-r1
- tool-calling
date: '2026-09-28'
---

Model Mimir diganti dari qwen2.5:7b-instruct + hermes3:8b (dua-duanya dihapus) menjadi qwen3:8b saja. deepseek-r1:8b juga dicoba tapi dihapus karena gagal total.

**Hasil uji (3 kali ulang tiap kasus, tool cari_outlet/cari_nama_outlet):**
- qwen3:8b: panggil tool untuk data outlet 3/3, rantai cari-nama-lalu-data 3/3, bilang "tidak ditemukan" dengan jelas 3/3, jawaban lanjutan benar 2/3, tidak pernah bocor JSON mentah -- sama atau lebih baik dari qwen2.5 di semua sisi.
- deepseek-r1:8b: TIDAK PERNAH memanggil tool untuk permintaan data langsung (0/3). Bukan cuma menolak -- dia MENGARANG template kosong yang meniru label output tool asli ("BULAN TERAKHIR", "Nilai per brand di bulan terakhir") tanpa data asli sama sekali. Ini lebih berbahaya daripada sekadar gagal, karena kelihatan seperti jawaban berbasis data padahal kosong.

**Kenapa:** tujuan Mimir adalah tidak pernah mengarang angka -- model yang mengarang BENTUK jawaban berbasis tool (bukan cuma menolak) adalah kegagalan paling berbahaya untuk kasus pemakaian ini, terlepas dari reputasi reasoning-nya.

**Cara menerapkan:** kalau mau coba model baru lagi nanti, ulangi pengujian yang sama (bukan cuma tanya sekali) -- cek apakah tool BENAR-benar terpanggil (tool_outputs terisi), bukan cuma percaya jawabannya kedengaran meyakinkan.
