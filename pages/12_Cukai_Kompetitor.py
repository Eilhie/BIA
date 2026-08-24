r"""
CUKAI KOMPETITOR
Estimasi volume kompetitor (Bintang/MBI, Anker, Bali Hai) dari data cukai --
satu-satunya cara mengetahui volume kompetitor karena angka penjualan mereka
sendiri tidak pernah kita punya. Dibaca langsung dari file kerja analis di
D:\cukai kompetitor (Cukai Kompetitor.xlsx, sheet REKAP RAPIH), TIDAK ditulis
apa pun dari sini -- editing datanya tetap di file Excel itu sendiri.

v1: cuma sheet REKAP RAPIH (perbandingan bulanan bersih). Folder itu juga
punya breakdown per wilayah/kota (FORMAT CUKAI WILAYAH.xlsx) dan data mentah
per-brand yang belum di-cover -- lihat cukai_pipeline.py.
"""

import pandas as pd
import streamlit as st

import auth
import cukai_pipeline as cp

auth.require_level(5, page="Cukai Kompetitor")
st.title("Cukai Kompetitor")
st.caption(
    f"Sumber: `{cp.REKAP_FILE}`, sheet `{cp.REKAP_SHEET}` -- estimasi volume kompetitor dari data "
    "cukai (pajak minuman beralkohol), murni baca & tampilkan, editing tetap di file Excel-nya "
    "sendiri. v1 baru cover tabel 'Bir OT vs Musuh'; breakdown per wilayah/kota belum di-include."
)

if not cp.is_available():
    st.error(f"File tidak ditemukan: `{cp.REKAP_FILE}`")
    st.stop()

last_mod = cp.get_last_modified()
st.caption(f"File terakhir diubah: {last_mod.strftime('%d %b %Y %H:%M') if last_mod else '-'}")

df = cp.load_rekap_rapih()
if df.empty:
    st.info("Tidak ada data yang terbaca dari sheet REKAP RAPIH.")
    st.stop()

brands = sorted(df["Brand"].unique())
picked_brands = st.multiselect("Brand", brands, default=brands, key="cukai_brands")

view = df[df["Brand"].isin(picked_brands)].sort_values(["Brand", "MonthDate"])

st.divider()
st.subheader("Tren volume (KRT, estimasi dari cukai)")

pivot_qty = view.pivot_table(index="MonthKey", columns="Brand", values="Qty", aggfunc="sum")
month_order = view.drop_duplicates("MonthKey").sort_values("MonthDate")["MonthKey"].tolist()
pivot_qty = pivot_qty.reindex(month_order)
st.line_chart(pivot_qty)

st.divider()
st.subheader("Kelengkapan data per brand")
st.caption(
    "Bulan terakhir yang punya angka > 0 -- kalau jauh dari bulan sekarang, kemungkinan "
    "data cukai brand itu belum diupdate di file sumbernya (bukan berarti volumenya benar-benar 0)."
)
gap_rows = []
for brand in brands:
    sub = df[df["Brand"] == brand].sort_values("MonthDate")
    nonzero = sub[sub["Qty"] > 0]
    last_month = nonzero["MonthKey"].iloc[-1] if not nonzero.empty else "-"
    gap_rows.append({"Brand": brand, "Bulan terakhir ada data": last_month})
st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Tabel detail (Qty + Share)")

table = view.copy()
table["Qty"] = table["Qty"].apply(lambda v: f"{v:,.0f}".replace(",", "."))
table["Share"] = table["Share"].apply(lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "-")
table = table[["Brand", "Month", "Qty", "Share"]].rename(columns={"Month": "Bulan", "Qty": "Qty (KRT)", "Share": "Pangsa"})
st.dataframe(table, use_container_width=True, hide_index=True)
