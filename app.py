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

from datetime import datetime

import streamlit as st

import auth
import daily_report_setup as drs

st.set_page_config(page_title="OMSET Seeker", layout="wide")

user = auth.get_current_user()

# (section buat grouping di sidebar, path relatif ke file ini, judul di menu &
# tab browser, jadikan default landing page)
PAGE_DEFS = [
    ("Utama", "pages/15_Home.py", "Home", True),
    ("Utama", "omset_search_app.py", "Omset Seeker", False),
    ("Utama", "pages/5_Outlet_Lapisan_MClub.py", "Outlet Lapisan MClub", False),
    ("Utama", "pages/3_Cek_Klaim_SKU.py", "Cek Klaim SKU", False),
    ("Utama", "pages/7_Detail_SKU_Brand_Besar.py", "Detail SKU Brand Besar", False),
    ("Utama", "pages/0_Dashboard.py", "Dashboard", False),
    ("Utama", "pages/2_SKU_Manifest.py", "SKU Manifest", False),
    ("Utama", "pages/13_BPR.py", "BPR", False),

    ("Sinkronisasi & Data", "pages/1_Sync_dan_Transpose.py", "Sync dan Transpose", False),
    ("Sinkronisasi & Data", "pages/11_EAO_Sync.py", "EAO Sync", False),
    ("Sinkronisasi & Data", "pages/4_Atur_SKU_Sync.py", "Atur SKU Sync", False),
    ("Sinkronisasi & Data", "pages/10_Atur_Gabungan_HOREKA.py", "Gabungan HOREKA", False),
    ("Sinkronisasi & Data", "pages/14_Atur_Gabungan_UMUM.py", "Gabungan UMUM", False),
    ("Sinkronisasi & Data", "pages/6_Cek_Cutoff_OMSHAR.py", "Cek Cutoff OMSHAR", False),
    ("Sinkronisasi & Data", "pages/12_Cukai_Kompetitor.py", "Cukai Kompetitor", False),
    ("Sinkronisasi & Data", "pages/16_Setup_Daily_Report.py", "Setup Daily Report", False),

    ("Admin", "pages/8_Kelola_User.py", "Kelola User", False),
    ("Admin", "pages/9_Audit_Trail.py", "Audit Trail", False),
]

sections: dict[str, list[st.Page]] = {}
for section, path, title, is_default in PAGE_DEFS:
    if user["level"] >= auth.PAGE_LEVELS.get(path, 99):
        sections.setdefault(section, []).append(st.Page(path, title=title, default=is_default))

if not sections:
    # st.navigation() error keras kalau daftarnya kosong -- bisa kejadian
    # nyata kalau Admin set level user ke 0 tanpa menonaktifkan akunnya
    # (dua hal beda: level 0 vs active=0), jadi TIDAK boleh dianggap "tidak
    # mungkin terjadi".
    st.title("Tidak ada akses")
    st.error(f"Akun **{user['username']}** (Level 0) belum diberi akses ke halaman manapun. Hubungi Admin.")
    st.stop()

# Identitas visual sama seperti layar login (auth._inject_auth_styles()) dan
# Home (pages/15_Home.py) -- font + aksen emas, supaya menu sidebar tidak
# terasa seperti Streamlit bawaan begitu saja.
st.sidebar.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=JetBrains+Mono:wght@500;600&display=swap">
    <style>
      section[data-testid="stSidebar"] { border-right: 1px solid rgba(200,134,42,0.18); }
      .sb-brand {
        font-family: 'Bebas Neue', Impact, sans-serif; font-size: 30px;
        letter-spacing: 0.02em; color: #c8862a; line-height: 1; padding: 4px 0 14px;
      }
      section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
      section[data-testid="stSidebar"] div[data-testid="stNavSectionHeader"] {
        border-radius: 6px;
      }
      section[data-testid="stSidebar"] a:hover {
        background: rgba(200,134,42,0.10) !important;
      }
      section[data-testid="stSidebar"] a[aria-current="page"] {
        background: rgba(200,134,42,0.16) !important;
        font-weight: 600;
      }
    </style>
    <div class="sb-brand">OMSET SEEKER</div>
    """,
    unsafe_allow_html=True,
)

# Modal notifikasi Setup Daily Report -- muncul di halaman APAPUN buat user
# Admin (level 5), bukan cuma kalau mereka kebetulan buka halaman
# "Setup Daily Report" sendiri. check_status() baca folder (scan disk) --
# supaya TIDAK jalan tiap rerun (Streamlit rerun script penuh tiap interaksi
# widget apa pun), hasilnya di-cache di session_state per TANGGAL, jadi scan
# beneran cuma terjadi sekali sehari per sesi. Modal sendiri juga cuma
# muncul sekali per hari (dismiss tersimpan per tanggal juga).
_today_str = str(datetime.now().date())


@st.dialog("Setup Daily Report")
def _daily_report_modal(status: dict):
    st.write(f"Folder hari ini: `{status['target']}`")
    st.warning(f"**{status['missing_count']} dari {status['total']}** file belum tersalin ke folder hari ini.")
    with st.expander("Lihat file yang belum tersalin"):
        for name in status["missing_names"]:
            st.write(f"- {name}")
    c1, c2 = st.columns(2)
    if c1.button("Jalankan Sekarang", type="primary"):
        drs.run_setup()
        st.session_state["_daily_report_dismissed_date"] = _today_str
        st.rerun()
    if c2.button("Nanti Saja"):
        st.session_state["_daily_report_dismissed_date"] = _today_str
        st.rerun()


if user["level"] >= 5:
    if st.session_state.get("_daily_report_checked_date") != _today_str:
        st.session_state["_daily_report_checked_date"] = _today_str
        st.session_state["_daily_report_status"] = drs.check_status()
    _status = st.session_state["_daily_report_status"]
    if _status["missing_count"] > 0 and st.session_state.get("_daily_report_dismissed_date") != _today_str:
        _daily_report_modal(_status)

nav = st.navigation(sections)
nav.run()
