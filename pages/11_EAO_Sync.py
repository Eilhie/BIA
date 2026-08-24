r"""
EAO SYNC
Monitoring untuk data EAO (sistem sell-out terpisah dari OMSHAR) -- sumbernya
server network \\10.4.1.25\Bev\EAO, disinkronkan otomatis ke D:\EAO tiap ~10
menit lewat Windows Task Scheduler + sync_eao.bat (robocopy, berjalan
independen dari app ini). Halaman ini kasih visibilitas: apa yang ada di
server (termasuk yang TIDAK ditarik otomatis), apa yang ada lokal, riwayat
sync, + tombol sync manual kalau butuh segera tanpa nunggu jadwal.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import auth
import eao_pipeline as ep

auth.require_level(5, page="EAO Sync")
st.title("EAO Sync")
st.caption(
    f"Sumber: `{ep.SERVER_BASE}` -- disinkronkan otomatis ke `{ep.LOCAL_DIR}` tiap ~10 menit "
    "lewat Task Scheduler (sync_eao.bat, berjalan independen). Halaman ini murni monitoring + "
    "tombol sync manual, tidak mengganggu jadwal otomatis yang sudah ada."
)


def _fmt_size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")


if not ep.is_server_reachable():
    st.error(
        f"Server `{ep.SERVER_BASE}` tidak terjangkau -- pastikan VPN aktif atau cek koneksi jaringan. "
        "Data di bawah cuma menampilkan status lokal (`D:\\EAO`)."
    )
else:
    st.success("Server terjangkau.")

now = datetime.now()
col_y, col_m = st.columns(2)
year = col_y.number_input("Tahun", min_value=2019, max_value=now.year + 1, value=now.year, key="eao_year")
month = col_m.number_input("Bulan", min_value=1, max_value=12, value=now.month, key="eao_month")

if st.button("Sync Sekarang", type="primary", key="eao_sync_btn"):
    with st.spinner("Menyalin file terbaru dari server..."):
        result = ep.sync_now(datetime(int(year), int(month), 1))
    if not result["ok"]:
        st.error(result["error"])
    elif result["copied"]:
        st.success(f"Disalin {len(result['copied'])} file baru: {', '.join(result['copied'])}")
    else:
        st.info("Semua file kunci sudah versi terbaru, tidak ada yang disalin.")

st.divider()
st.subheader("Perbandingan server vs lokal (bulan yang dipilih)")

srv = ep.list_server_month(int(year), int(month))
if not srv["found"]:
    st.warning(f"Folder {year}-{month:02d} belum ada di server.")
else:
    st.caption(f"Folder server: `{srv['folder']}`")
    local_names = {f["name"] for f in ep.list_local_files()}

    rows = []
    for subdir, files in [("Daily", srv["daily"]), ("Monthly", srv["monthly"])]:
        for f in files:
            is_key = any(f["name"].endswith(p) for p in ep.KEY_PATTERNS)
            rows.append({
                "Folder": subdir,
                "File": f["name"],
                "Ukuran": _fmt_size(f["size"]),
                "Diubah (server)": _fmt_time(f["mtime"]),
                "Ditarik otomatis?": "Ya" if is_key else "Tidak",
                "Ada di lokal?": "Ya" if f["name"] in local_names else "Tidak",
            })

    if rows:
        df = pd.DataFrame(rows)
        missing = df[(df["Ditarik otomatis?"] == "Ya") & (df["Ada di lokal?"] == "Tidak")]
        if not missing.empty:
            st.warning(
                f"{len(missing)} file kunci ada di server tapi belum ada lokal -- "
                "kemungkinan sync otomatis belum sempat jalan, atau server baru saja update."
            )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Tidak ada file di folder bulan ini.")

st.divider()
st.subheader("File lokal (D:\\EAO)")
local_files = ep.list_local_files()
if local_files:
    df_local = pd.DataFrame([
        {
            "File": f["name"],
            "Ukuran": _fmt_size(f["size"]),
            "Diubah": _fmt_time(f["mtime"]),
            "Kunci (auto-sync)": "Ya" if f["is_key"] else "Tidak",
        }
        for f in local_files
    ])
    st.dataframe(df_local, use_container_width=True, hide_index=True)
else:
    st.info("Belum ada file di D:\\EAO.")

st.divider()
st.subheader("Riwayat sync (30 terakhir)")
log_lines = ep.read_sync_log(30)
if log_lines:
    st.code("\n".join(log_lines), language=None)
else:
    st.caption("Belum ada log sync.")
