r"""
CUKAI KOMPETITOR
Estimasi volume kompetitor (Bintang/MBI, Anker, Bali Hai) dari data cukai --
satu-satunya cara mengetahui volume kompetitor karena angka penjualan mereka
sendiri tidak pernah kita punya. Dibaca langsung dari file kerja analis di
D:\cukai kompetitor (Cukai Kompetitor.xlsx, sheet REKAP RAPIH), TIDAK ditulis
apa pun dari sini -- editing datanya tetap di file Excel itu sendiri.

Cover tabel rekap "Bir OT vs Musuh" (REKAP RAPIH) + sheet detail per kompetitor
(Balihai/Delta, Lokal/Export) sampai level kemasan/SKU. Folder itu juga punya
breakdown per wilayah/kota (FORMAT CUKAI WILAYAH.xlsx) yang belum di-cover --
lihat cukai_pipeline.py.
"""

import pandas as pd
import streamlit as st

import auth
import cukai_pipeline as cp

@st.cache_data(show_spinner=False, ttl="10m")
def get_rekap_rapih() -> pd.DataFrame:
    return cp.load_rekap_rapih()


@st.cache_data(show_spinner=False, ttl="10m")
def get_detail_sheet(sheet_key: str) -> pd.DataFrame:
    return cp.load_detail_sheet(sheet_key)


auth.require_level(5, page="Cukai Kompetitor")
st.title("Cukai Kompetitor")
st.caption(
    f"Sumber: `{cp.REKAP_FILE}` -- estimasi volume kompetitor dari data cukai (pajak minuman "
    "beralkohol), murni baca & tampilkan, editing tetap di file Excel-nya sendiri. Breakdown per "
    "wilayah/kota belum di-include."
)

if not cp.is_available():
    st.error(f"File tidak ditemukan: `{cp.REKAP_FILE}`")
    st.stop()

last_mod = cp.get_last_modified()
st.caption(f"File terakhir diubah: {last_mod.strftime('%d %b %Y %H:%M') if last_mod else '-'}")

tab_rekap, tab_detail = st.tabs(["Rekap Bir OT vs Musuh", "Detail per Kompetitor (Balihai/Delta)"])

with tab_rekap:
    with st.spinner("Memuat REKAP RAPIH..."):
        df = get_rekap_rapih()
    if df.empty:
        st.info("Tidak ada data yang terbaca dari sheet REKAP RAPIH.")
    else:
        brands = sorted(df["Brand"].unique())
        picked_brands = st.multiselect("Brand", brands, default=brands, key="cukai_brands")

        view = df[df["Brand"].isin(picked_brands)].sort_values(["Brand", "MonthDate"])
        view = cp.collapse_past_years(view, group_cols=["Brand"], value_cols=["Qty", "Share"])
        month_order = view.drop_duplicates("Period").sort_values("PeriodDate")["Period"].tolist()
        st.caption(
            "Tahun-tahun lalu diringkas jadi satu titik rata-rata (**Rata2 20XX**) -- tahun berjalan "
            "tetap per-bulan, biar fokus ke yang terbaru tanpa kehilangan histori sama sekali."
        )

        st.subheader("Volume per bulan (KRT, estimasi dari cukai)")
        pivot_qty = view.pivot_table(index="Period", columns="Brand", values="Qty", aggfunc="sum")
        pivot_qty = pivot_qty.reindex(month_order)
        st.bar_chart(pivot_qty)

        st.subheader("Pangsa pasar per bulan")
        pivot_share = view.pivot_table(index="Period", columns="Brand", values="Share", aggfunc="sum")
        pivot_share = pivot_share.reindex(month_order)
        st.bar_chart(pivot_share)

        st.divider()
        col_qty, col_gap = st.columns([3, 1])
        with col_gap:
            st.caption("**Kelengkapan data**")
            st.caption(
                "Bulan terakhir dengan angka > 0. Kalau jauh dari bulan sekarang, kemungkinan data "
                "cukai brand itu belum diupdate di sumbernya (bukan berarti volumenya benar-benar 0)."
            )
            gap_rows = []
            for brand in brands:
                sub = df[df["Brand"] == brand].sort_values("MonthDate")
                nonzero = sub[sub["Qty"] > 0]
                last_month = nonzero["MonthKey"].iloc[-1] if not nonzero.empty else "-"
                is_stale = brand in picked_brands and last_month != month_order[-1] if month_order else False
                gap_rows.append({"Brand": brand, "Update terakhir": ("⚠️ " if is_stale else "") + last_month})
            st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)

        with col_qty:
            st.caption("**Tabel Qty (KRT) -- warna makin gelap = volume makin besar, baca cepat per baris/kolom**")
            pivot_qty_disp = pivot_qty.T.reindex(columns=month_order)
            st.dataframe(
                pivot_qty_disp.style
                    .background_gradient(cmap="Blues", axis=None)
                    .format(lambda v: f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "-"),
                use_container_width=True,
            )

            st.caption("**Tabel Pangsa Pasar -- warna makin gelap = pangsa makin besar**")
            pivot_share_disp = pivot_share.T.reindex(columns=month_order)
            st.dataframe(
                pivot_share_disp.style
                    .background_gradient(cmap="Greens", axis=None, vmin=0, vmax=1)
                    .format(lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "-"),
                use_container_width=True,
            )

with tab_detail:
    st.caption(
        "Replika sheet detail per kompetitor -- pecah sampai level kemasan/SKU. Baris **tebal** "
        "(bold) = total brand/varian, baris biasa di bawahnya = rincian kemasan penyusunnya "
        "(sama persis dengan format di file Excel-nya)."
    )
    sheet_key = st.radio("Sheet", list(cp.DETAIL_SHEETS.keys()), horizontal=True, key="cukai_detail_sheet")

    with st.spinner(f"Memuat sheet {sheet_key}..."):
        detail_df = get_detail_sheet(sheet_key)
    if detail_df.empty:
        st.info("Tidak ada data yang terbaca dari sheet ini.")
    else:
        col_search, col_toggle = st.columns([3, 1])
        query = col_search.text_input("Cari brand/kemasan", key="cukai_detail_query")
        only_total = col_toggle.checkbox("Total saja (sembunyikan detail SKU)", value=True, key="cukai_detail_only_total")

        rows_df = detail_df[["Baris", "IsTotal"]].drop_duplicates()
        if only_total:
            rows_df = rows_df[rows_df["IsTotal"]]
        if query.strip():
            rows_df = rows_df[rows_df["Baris"].str.lower().str.contains(query.strip().lower())]

        picked_rows = rows_df["Baris"].tolist()
        sub = detail_df[detail_df["Baris"].isin(picked_rows)]

        if sub.empty:
            st.info("Tidak ada baris yang cocok.")
        else:
            st.caption(f"{len(picked_rows)} baris ditampilkan (dari {detail_df['Baris'].nunique()} total di sheet ini).")
            st.caption(
                "Tahun-tahun lalu diringkas jadi satu titik rata-rata (**Rata2 20XX**) -- tahun berjalan "
                "tetap per-bulan."
            )

            sub = cp.collapse_past_years(sub, group_cols=["Baris", "IsTotal"], value_cols=["Qty", "Liter"])
            pivot_qty = sub.pivot_table(index="Baris", columns="Period", values="Qty", aggfunc="sum")
            month_order = sub.drop_duplicates("Period").sort_values("PeriodDate")["Period"].tolist()
            pivot_qty = pivot_qty.reindex(columns=month_order)
            pivot_qty = pivot_qty.reindex(index=[r for r in picked_rows if r in pivot_qty.index])

            st.subheader("Qty (KRT) per bulan")
            st.caption("Warna makin gelap = volume makin besar, baca cepat per baris/kolom.")
            st.dataframe(
                pivot_qty.style
                    .background_gradient(cmap="Blues", axis=None)
                    .format(lambda v: f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "-"),
                use_container_width=True,
            )

            if len(picked_rows) <= 15:
                st.subheader("Tren (bar)")
                st.bar_chart(pivot_qty.T)
