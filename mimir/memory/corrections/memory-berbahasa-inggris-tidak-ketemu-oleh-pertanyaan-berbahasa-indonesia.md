---
name: memory-berbahasa-inggris-tidak-ketemu-oleh-pertanyaan-berbahasa-indonesia
type: correction
tags:
- mimir
- embedding
- bahasa
- retrieval
date: '2026-09-21'
---

Model embedding nomic-embed-text condong ke bahasa Inggris: memory yang ditulis dalam bahasa Inggris hampir tidak ditemukan oleh pertanyaan berbahasa Indonesia.

**Bukti:** memory berbahasa Inggris dengan pertanyaan Inggris muncul di peringkat 1 (jarak 0.517), tetapi dengan pertanyaan Indonesia jatuh ke peringkat 46 (jarak 0.94). Kontrolnya, memory berbahasa Indonesia dengan pertanyaan Indonesia, peringkat 1.

**Cara menerapkan:** tulis memory dan dokumentasi dalam bahasa yang akan dipakai untuk bertanya (Indonesia), atau ganti embedding dengan model multibahasa sebelum memindahkan dokumentasi ke bahasa Inggris -- kalau tidak, pencarian Mimir akan memburuk pelan-pelan seiring dokumentasi berpindah bahasa.
