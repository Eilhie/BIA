"""
GABUNGAN HOREKA
Status & isi grup gabungan HOREKA -- sumbernya file Excel eksternal
"Gabungan HOREKA Update {tgl} {bulan} {tahun}.xlsx" di folder yang sama
dengan Toko Gabungan UMUM (D:\\Data BIA\\INFO BIA\\Toko Gabungan), TAPI format
beda: SATU SHEET = SATU GRUP (nama sheet = nama grup), tiap baris di sheet
itu satu outlet anggota (kolom SITE/OUTLET/WILAYAH, urutan bebas).

Halaman ini cuma BACA & TAMPILKAN -- editing grupnya dilakukan di file Excel
itu sendiri (sama seperti Toko Gabungan UMUM), bukan lewat form di app ini.
"""

import pandas as pd
import streamlit as st

import auth
import omset_seeker as os_

auth.require_level(5, page="Gabungan HOREKA")
st.title("Gabungan HOREKA")
st.caption(
    "Grup gabungan HOREKA dibaca dari file Excel terpisah -- **satu sheet = satu grup** "
    "(nama sheet jadi nama grup), tiap baris di sheet itu satu outlet anggota dengan "
    "kolom SITE, OUTLET, WILAYAH. Sekali file ini di-update, grup gabungannya otomatis "
    "muncul di pencarian Omset Seeker grup HOREKA dan angkanya dijumlah dari semua "
    "toko anaknya -- persis seperti Toko Gabungan UMUM."
)

col_cap, col_btn = st.columns([5, 1])
col_cap.caption(f"Sumber: `{os_.TOKO_GABUNGAN_DIR}` -- pola nama file: `Gabungan HOREKA Update <tgl> <bulan> <tahun>.xlsx`")
if col_btn.button("Refresh"):
    os_.load_horeka_gabungan_map.cache_clear()
    os_.load_gabungan_map.cache_clear()
    st.rerun()

gab_path = os_.find_latest_horeka_gabungan()
if gab_path is None:
    st.warning(
        "File 'Gabungan HOREKA Update ...' belum ditemukan di folder itu. Buat file baru "
        "dengan pola nama itu (persis, termasuk tanggal dalam Bahasa Indonesia, mis. "
        "'Gabungan HOREKA Update 11 Agustus 2026.xlsx'), satu sheet per grup, kolom "
        "SITE/OUTLET/WILAYAH di baris pertama tiap sheet."
    )
else:
    gab_map = os_.load_gabungan_map("HOREKA")
    g1, g2 = st.columns(2)
    g1.metric("File aktif", gab_path.name)
    g2.metric("Jumlah grup gabungan", len(gab_map))

    st.divider()

    if not gab_map:
        st.info(
            "File ditemukan tapi tidak ada sheet yang cocok formatnya (butuh header "
            "SITE dan WILAYAH di baris pertama, minimal 2 outlet per sheet)."
        )
    else:
        outlet_names_horeka = os_.build_outlet_index("HOREKA").set_index("Site")["Outlet"].to_dict()
        for gab_site, g in sorted(gab_map.items(), key=lambda kv: kv[1]["name"]):
            with st.expander(f"{g['name']} -- {g['wilayah']} -- {len(g['children'])} toko"):
                st.caption(f"Kode gabungan: `{gab_site}`")
                rows = [
                    {"Site": s, "Outlet (data HOREKA saat ini)": outlet_names_horeka.get(s, "(tidak ditemukan)")}
                    for s in g["children"]
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
