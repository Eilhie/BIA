"""
GABUNGAN UMUM
Status & isi grup gabungan UMUM -- sumbernya file Excel eksternal dari divisi
lain di folder D:\\Data BIA\\INFO BIA\\Toko Gabungan, DUA pola nama dikenali
(lihat find_latest_toko_gabungan() di omset_seeker.py):
  - "Toko Gabungan Update {tgl} {bulan} {tahun}.xlsx" (konvensi lama, satu
    sheet 'A11' berformat blok, atau sheet 'Sheet1' berformat flat)
  - "Toko Gabungan (Formula Live) - Data {bulan} {tahun}.xlsx" (konvensi baru,
    tanpa tanggal harian -- dianggap menang atas file 'Update' bulan yang sama)

Halaman ini cuma BACA & TAMPILKAN -- editing grupnya dilakukan di file Excel
itu sendiri (sama seperti Gabungan HOREKA), bukan lewat form di app ini.
"""

import pandas as pd
import streamlit as st

import auth
import omset_seeker as os_

auth.require_level(5, page="Gabungan UMUM")
st.title("Gabungan UMUM")
st.caption(
    "Grup gabungan UMUM dibaca dari file Excel eksternal (divisi lain) -- file 'Update' "
    "bulanan lama (blok atau flat) ATAU file 'Formula Live' yang lebih baru, mana pun yang "
    "lebih baru dipakai otomatis. Sekali file itu di-update, grup gabungannya otomatis "
    "muncul di pencarian Omset Seeker grup UMUM dan angkanya dijumlah dari semua toko "
    "anaknya -- persis seperti Gabungan HOREKA."
)

col_cap, col_btn = st.columns([5, 1])
col_cap.caption(f"Sumber: `{os_.TOKO_GABUNGAN_DIR}` -- pola nama: `Toko Gabungan Update <tgl> <bulan> <tahun>.xlsx` atau `Toko Gabungan (Formula Live) - Data <bulan> <tahun>.xlsx`")
if col_btn.button("Refresh"):
    os_.load_gabungan_map.cache_clear()
    st.rerun()

gab_path = os_.find_latest_toko_gabungan()
if gab_path is None:
    st.warning(
        "File 'Toko Gabungan Update ...' atau 'Toko Gabungan (Formula Live) ...' belum "
        "ditemukan di folder itu dengan pola nama yang dikenali."
    )
else:
    # File ini bisa besar (puluhan ribu baris) -- parse pertama per sesi/setelah cache
    # di-clear terukur nyata ~2 menit, jauh lebih lama dari halaman lain di app ini.
    # Spinner + caption di sini supaya kelihatan masih jalan, bukan macet.
    with st.spinner(f"Memuat {gab_path.name}... (bisa ~1-2 menit untuk file besar, cuma sekali sampai di-Refresh)"):
        gab_map = os_.load_gabungan_map("UMUM")

    g1, g2 = st.columns(2)
    g1.metric("File aktif", gab_path.name)
    g2.metric("Jumlah grup gabungan", len(gab_map))

    st.divider()

    if not gab_map:
        st.info(
            "File ditemukan tapi tidak ada grup yang cocok formatnya -- butuh sheet 'Sheet1' "
            "(flat, kolom WIL/SITE/CUST/GROUP) atau blok di sheet pertama (baris toko diikuti "
            "satu baris ringkasan gabungan)."
        )
    else:
        outlet_names_umum = os_.build_outlet_index("UMUM").set_index("Site")["Outlet"].to_dict()
        for gab_site, g in sorted(gab_map.items(), key=lambda kv: kv[1]["name"]):
            with st.expander(f"{g['name']} -- {g['wilayah']} -- {len(g['children'])} toko"):
                st.caption(f"Kode gabungan: `{gab_site}`")
                rows = [
                    {"Site": s, "Outlet (data UMUM saat ini)": outlet_names_umum.get(s, "(tidak ditemukan)")}
                    for s in g["children"]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
