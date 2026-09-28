---
name: cari-outlet-render-tabel-html-asli-heimdall-bukan-teks-llm
type: decision
tags:
- mimir
- tools
- render
- omset-seeker
date: '2026-09-28'
---

tools.py cari_outlet() sekarang juga memanggil core/render_outlet_image.py (build_report_rows + build_html_table) -- fungsi render yang SAMA dipakai halaman Omset Seeker asli -- lalu ditampilkan di panel tool Mimir lewat st.markdown(html, unsafe_allow_html=True).

**Kenapa:** sebelumnya angka omset cuma disampaikan sebagai narasi/bullet list oleh LLM. User minta tampilan yang sama seperti laporan asli di Omset Seeker, bukan cuma tabel biasa -- lebih penting lagi, ini juga mengurangi risiko LLM salah tulis ulang angka jadi teks (lihat memory 'cek-angka-jawaban-tool-per-sel'), karena sekarang user bisa langsung lihat tabel resminya, tidak cuma percaya kalimat model.

**Cara menerapkan:** render HTML itu gagal-aman -- dibungkus try/except terpisah dari model_text (yang tetap dihitung manual, bukan dari render_outlet_image), jadi kalau render HTML gagal, jawaban tetap muncul (cuma tanpa tabel visual).

**Catatan operasional yang ditemukan saat kerjakan ini:** sistem sempat kehabisan memori (OpenBLAS/pandas error) waktu diuji -- ternyata BUKAN bug kode, tapi ada proses transpose.py all beneran sedang jalan (dari Heimdall mode LAN, kemungkinan rekan kerja lain), memakai ~20 proses paralel dan hampir semua RAM. Pelajaran: kalau ada error out-of-memory pas testing, cek dulu proses lain yang jalan (Get-Process) sebelum curiga ke kode sendiri.
