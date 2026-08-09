"""
app.py
Entry point BARU (dijalankan lewat CARI OUTLET.bat / CARI OUTLET (LAN).bat,
gantikan omset_search_app.py sebagai target langsung `streamlit run`).

Kenapa perlu file ini: sebelumnya Streamlit otomatis membangun menu sidebar
dari SEMUA file di pages/ tanpa peduli level user -- halaman yang tidak boleh
diakses tetap MUNCUL di menu, cuma diblokir (pesan "Akses ditolak") begitu
diklik. User yang levelnya rendah jadi lihat menu penuh berisi halaman yang
tidak relevan buat mereka.

st.navigation()/st.Page() (API MPA terprogram Streamlit) menggantikan
auto-discovery itu dengan daftar eksplisit yang kita bangun sendiri di sini,
di-filter per user SEBELUM menu dirender -- jadi halaman yang levelnya tidak
cukup memang tidak pernah muncul di menu sama sekali, bukan cuma diblokir
pas diklik. auth.require_level() di masing-masing halaman TETAP dipertahankan
sebagai lapis kedua (jaga-jaga akses langsung lewat URL).

set_page_config() HARUS di sini (satu-satunya tempat) -- kalau halaman tujuan
juga memanggilnya, Streamlit error "can only be called once per app".
"""

import streamlit as st

import auth

st.set_page_config(page_title="OMSET Seeker", layout="wide")

user = auth.get_current_user()

# (path relatif ke file ini, judul di menu & tab browser, jadikan default landing page)
PAGE_DEFS = [
    ("omset_search_app.py", "Omset Seeker", True),
    ("pages/0_Dashboard.py", "Dashboard", False),
    ("pages/2_SKU_Manifest.py", "SKU Manifest", False),
    ("pages/5_Outlet_Lapisan_MClub.py", "Outlet Lapisan MClub", False),
    ("pages/6_Cek_Cutoff_OMSHAR.py", "Cek Cutoff OMSHAR", False),
    ("pages/7_Detail_SKU_Brand_Besar.py", "Detail SKU Brand Besar", False),
    ("pages/3_Cek_Klaim_SKU.py", "Cek Klaim SKU", False),
    ("pages/4_Atur_SKU_Sync.py", "Atur SKU Sync", False),
    ("pages/1_Sync_dan_Transpose.py", "Sync dan Transpose", False),
    ("pages/8_Kelola_User.py", "Kelola User", False),
]

visible_pages = [
    st.Page(path, title=title, default=is_default)
    for path, title, is_default in PAGE_DEFS
    if user["level"] >= auth.PAGE_LEVELS.get(path, 99)
]

if not visible_pages:
    # st.navigation() error keras kalau daftarnya kosong -- bisa kejadian
    # nyata kalau Admin set level user ke 0 tanpa menonaktifkan akunnya
    # (dua hal beda: level 0 vs active=0), jadi TIDAK boleh dianggap "tidak
    # mungkin terjadi".
    st.title("Tidak ada akses")
    st.error(f"Akun **{user['username']}** (Level 0) belum diberi akses ke halaman manapun. Hubungi Admin.")
    st.stop()

nav = st.navigation(visible_pages)
nav.run()
