---
name: tool-mimir-dibatasi-hanya-untuk-pencarian-outlet
type: decision
tags:
- mimir
- tool
- akses
- heimdall
date: '2026-09-21'
---

Tool-calling Mimir (tools.py) hanya membuka dua fungsi: cari_outlet dan cari_nama_outlet -- setara halaman Omset Seeker di Heimdall (level akses 1).

**Kenapa:** Heimdall mengunci data klaim SKU dan dashboard di balik login Admin (level 0-5 di config/config.yaml). Mimir tidak punya login sama sekali, jadi tool apa pun yang membuka data itu akan diam-diam melewati kunci tersebut untuk siapa saja yang duduk di PC ini.

**Cara menerapkan:** sebelum menambah tool yang membaca data di atas level 1 (sku_lookup, cutoff, info dashboard), putuskan dulu soal kontrol akses -- misalnya beri Mimir login atau level per-user -- jangan cuma mendaftarkan fungsinya.
