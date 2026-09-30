"""
OMSET P90
Rekap omset channel "Pasar 90" (key account/modern trade -- Ranch Market,
Foodhall, Grand Lucky, dst) dari arsip Google Drive "Omshar Div AB1, FABS,
PROST dan Bev B&C" -- BEDA dari OMSHAR biasa (per-wilayah): di sini per
KEY ACCOUNT (banner/chain) atau per OUTLET INDIVIDUAL, dengan subtotal
Triwulan (TW) + RT2 + rasio RT2 tahun-ke-tahun, meniru format yang sudah
dipakai manual di "OMS OUTLET P90 2026.xlsx".

Layout (sidebar browse + klik -> hasil di area utama) SENGAJA dibuat sama
seperti omset_search_app.py (Omset Seeker) -- satu pola interaksi yang
sama dipakai di seluruh app, bukan pola baru per halaman.

WIP -- baru pakai arsip DIV AB1 (35 brand leaf, paling lengkap dari 3 arsip
yang ada). Sheet kategori "GG*" (mis. GGPR-GPROST) sengaja belum dipakai
(lihat catatan is_brand_group_sheet() di omshar90_pipeline.py) -- kalau
nanti komposisinya dipastikan, bisa ditambah subtotal per kategori. Nama
brand juga masih kode mentah (item_code, mis. "SB-GAMERAJA") -- menunggu
daftar nama resmi per item dari user.
"""

from pathlib import Path
import tempfile

import pandas as pd
import py7zr
import streamlit as st
import xlrd

from core import auth
from omshar90 import omshar90_pipeline as op
from omshar90 import render_p90 as rp

auth.require_level(5, page="Omset P90")
st.title("Omset P90")
st.caption(
    "Sumber: Google Drive (arsip \"Omshar Div AB1, FABS, PROST dan Bev B&C\", "
    "file `omshar90 DIV AB1'26.xls`, 35 brand)."
)

MAX_LIST_RESULTS = 30


@st.cache_data(show_spinner=False, ttl="30m")
def _load() -> pd.DataFrame:
    return op.load_data("DIV_AB1")


@st.cache_data(show_spinner=False, ttl="30m")
def _load_as_of():
    archives = op.find_archives()
    path = archives.get("DIV_AB1")
    if path is None:
        return None
    with py7zr.SevenZipFile(path, mode="r") as z:
        names = z.getnames()
        xls_name = next((n for n in names if n.lower().startswith("omshar90")), None)
        if xls_name is None:
            return None
        with tempfile.TemporaryDirectory() as tmp_dir:
            z.extract(path=tmp_dir, targets=[xls_name])
            wb = xlrd.open_workbook(str(Path(tmp_dir) / xls_name), on_demand=True)
            as_of = op.data_as_of_date(wb.sheet_by_index(0))
            wb.release_resources()
            return as_of


with st.spinner("Membaca data OMSHAR90 dari Drive..."):
    df = _load()

if df.empty:
    st.error(
        "Data tidak ditemukan -- arsip DIV AB1 belum muncul di Drive hari ini, "
        "atau file `omshar90 ...` di dalamnya tidak terbaca."
    )
    st.stop()

as_of = _load_as_of()
if as_of:
    st.caption(f"Data per tanggal: **{as_of.strftime('%d %B %Y')}** (H-1 dari tanggal PERIODE di file).")


def pick_key_account(key_acc: str) -> None:
    st.session_state["p90_last_query"] = ("key_account", key_acc)


def pick_outlet(site: str) -> None:
    st.session_state["p90_last_query"] = ("outlet", site)


with st.sidebar:
    st.header("Daftar Omset P90")
    list_type = st.radio("Lihat berdasarkan", ["Key Account", "Outlet Individual"], horizontal=True, key="p90_list_type")

    list_query = st.text_input("Cari nama/kode", key="p90_list_query", placeholder="ketik untuk mencari...")
    q = list_query.strip().lower()

    if list_type == "Key Account":
        counts = df.drop_duplicates("Site").groupby("KeyAcc")["Site"].count().sort_values(ascending=False)
        matches = counts
        if q:
            matches = matches[matches.index.str.lower().str.contains(q, na=False)]
        n = len(matches)
        if n == 0:
            st.caption("Tidak ada key account yang cocok.")
        else:
            shown = matches.head(MAX_LIST_RESULTS)
            st.caption(f"{n} key account" + (f" (menampilkan {MAX_LIST_RESULTS} teratas)" if n > MAX_LIST_RESULTS else ""))
            for key_acc, cnt in shown.items():
                st.button(
                    f"{key_acc}  \n{cnt} outlet",
                    key=f"pick_ka_{key_acc}",
                    use_container_width=True,
                    on_click=pick_key_account,
                    args=(key_acc,),
                )
    else:
        outlets = df.drop_duplicates("Site")[["Site", "Cust", "KeyAcc"]].sort_values("Cust")
        matches = outlets
        if q:
            matches = matches[
                matches["Cust"].str.lower().str.contains(q, na=False, regex=False)
                | matches["Site"].str.lower().str.contains(q, na=False, regex=False)
            ]
        n = len(matches)
        if q == "":
            st.caption("Ketik nama/kode outlet untuk mulai mencari.")
        elif n == 0:
            st.caption("Tidak ada outlet yang cocok.")
        else:
            shown = matches.head(MAX_LIST_RESULTS)
            st.caption(f"{n} hasil" + (f" (menampilkan {MAX_LIST_RESULTS} teratas)" if n > MAX_LIST_RESULTS else ""))
            for _, row in shown.iterrows():
                st.button(
                    f"{row['Cust']}  \n{row['Site']} · {row['KeyAcc']}",
                    key=f"pick_outlet_{row['Site']}",
                    use_container_width=True,
                    on_click=pick_outlet,
                    args=(row["Site"],),
                )

if "p90_last_query" in st.session_state:
    q_kind, q_value = st.session_state["p90_last_query"]

    if q_kind == "key_account":
        key_acc = q_value
        members = df[df["KeyAcc"] == key_acc].drop_duplicates("Site")[["Site", "Cust"]]

        st.subheader(f"Key Account: {key_acc}")
        meta_cols = st.columns(3)
        meta_cols[0].metric("Key Account", key_acc)
        meta_cols[1].metric("Jumlah Outlet", len(members))
        meta_cols[2].metric("Sumber", "DIV AB1")
        with st.expander("Lihat daftar outlet"):
            st.dataframe(members, use_container_width=True, hide_index=True)

        rekap_ka = op.compute_rekap_key_account(df)
        subset = rekap_ka[rekap_ka["KeyAcc"] == key_acc]
        table = rp.build_display_table(subset, label_col="item_code", label_header="BRAND")
        file_stem = f"Omset P90 - {key_acc}"

    else:
        site = q_value
        outlets = df.drop_duplicates("Site")[["Site", "Cust", "KeyAcc"]]
        info_row = outlets[outlets["Site"] == site].iloc[0]

        st.subheader(info_row["Cust"])
        meta_cols = st.columns(3)
        meta_cols[0].metric("Site", info_row["Site"])
        meta_cols[1].metric("Key Account", info_row["KeyAcc"])
        meta_cols[2].metric("Sumber", "DIV AB1")

        outlet_rekap = op.compute_rekap_outlet(df, site)
        table = rp.build_display_table(outlet_rekap, label_col="item_code", label_header="BRAND")
        file_stem = f"Omset P90 - {info_row['Site']} {info_row['Cust']}"

    st.markdown(rp.build_html_table(table, label_header="BRAND"), unsafe_allow_html=True)

    buf = pd.io.common.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        table.to_excel(writer, index=False, sheet_name="Omset P90")
    st.download_button(
        "Download Excel",
        data=buf.getvalue(),
        file_name=f"{file_stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Pilih Key Account atau cari outlet di sidebar untuk mulai.")
