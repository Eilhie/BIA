"""
OUTLET LAPISAN (MCLUB)
Otomatisasi klasifikasi tier outlet Gold/Platinum/MCLUB + analisis kompetitif
(OMS LOSS, INDUSTRI, pangsa pasar) dari file RAW yang diterima dari divisi lain.
Menggantikan proses manual maintain file kerja 55MB/13MB + REKAP + PDF.
"""

import io

import pandas as pd
import streamlit as st

import mclub_pipeline as mp

st.set_page_config(page_title="Outlet Lapisan (MClub)", layout="wide")
st.title("Outlet Lapisan (MClub)")
st.caption(
    "Klasifikasi tier outlet (Gold/Platinum/MCLUB) + analisis kompetitif, dihitung "
    "otomatis dari file RAW yang diterima dari divisi lain -- semua rumus di bawah "
    "sudah diverifikasi persis terhadap file kerja Excel yang ada sekarang."
)

METRIC_LABELS = {
    "SMT2_25": "SMT2 25", "SMT1_26": "SMT1 26", "OMS_LOSS": "OMS Loss",
    "PCT_SMT1_VS_SMT2": "% SMT1 vs SMT2", "PCT_SMT1_VS_RT25": "% SMT1 vs RT2 25",
    "TOTAL_MUSUH": "Total Musuh", "INDUSTRI": "Industri",
    "PCT_BIR_VS_MUSUH": "% BIR vs Musuh", "PCT_BIR_VS_INDUSTRI": "% BIR vs Industri",
}

category = st.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="mclub_cat")

st.divider()
st.subheader("1. Seed archive dari file kerja lama (sekali saja)")
st.caption(
    f"Import histori dari `{mp.WORKING_FILE[category].name}` yang sudah ada -- "
    "sekali jalan di awal biar riwayat bulan-bulan lama tidak hilang."
)

existing = mp.load_archive(category)

if st.button("Import dari file kerja lama", key="seed_btn"):
    if not existing.empty:
        st.session_state["mclub_confirm_seed"] = category
    else:
        with st.spinner("Membaca file kerja (ukurannya besar, bisa lambat)..."):
            seeded = mp.seed_archive_from_working_file(category)
            mp.save_archive(seeded, category)
        st.success(f"Archive diisi dari file kerja: {len(seeded)} outlet.")
        st.rerun()

if st.session_state.get("mclub_confirm_seed") == category:
    st.warning(
        f"Archive {category} sudah punya {len(existing)} outlet. Import ulang dari file kerja "
        "bisa TIMPA data yang lebih baru (kalau sudah pernah proses RAW terbaru) dengan data "
        "lama dari file kerja. Yakin lanjut?"
    )
    c1, c2 = st.columns(2)
    if c1.button("Ya, gabung dengan file kerja", key="seed_confirm_yes"):
        with st.spinner("Membaca file kerja..."):
            seeded = mp.seed_archive_from_working_file(category)
            merged = mp.merge_into_archive(existing, seeded)
            mp.save_archive(merged, category)
        del st.session_state["mclub_confirm_seed"]
        st.success(f"Archive diperbarui: {len(merged)} outlet.")
        st.rerun()
    if c2.button("Batal", key="seed_confirm_no"):
        del st.session_state["mclub_confirm_seed"]
        st.rerun()

st.divider()
st.subheader("2. Proses file RAW baru")
st.caption(
    "Upload file RAW dari divisi lain -- bulan baru ditambahkan ke archive, "
    "bulan yang tumpang tindih (biasanya 1-2 bulan terakhir) ditimpa versi terbaru."
)

uploaded = st.file_uploader(f"Upload RAW {category} (.xlsx)", type=["xlsx"], key="mclub_upload")
if uploaded is not None and st.button("Proses RAW ini", type="primary", key="mclub_process"):
    with st.spinner("Membaca & menggabungkan ke archive..."):
        parser = mp.parse_raw_umum if category == "UMUM" else mp.parse_raw_horeka
        try:
            raw_df = parser(uploaded)
        except ValueError as e:
            st.error(f"Gagal baca file RAW: {e}")
            raw_df = None
        if raw_df is not None:
            archive = mp.load_archive(category)
            merged = mp.merge_into_archive(archive, raw_df)
            mp.save_archive(merged, category)
            st.success(f"RAW diproses: {len(raw_df)} baris digabung, total archive sekarang {len(merged)} outlet.")
            st.rerun()

st.divider()
st.subheader("3. Lihat & cari hasil")

archive = mp.load_archive(category)
if archive.empty:
    st.info("Archive masih kosong. Lakukan langkah 1 atau 2 dulu.")
else:
    result = mp.compute_metrics(archive, category=category)

    col1, col2 = st.columns([2, 1])
    query = col1.text_input("Cari outlet (nama/kode)", key="mclub_query")
    lapisan_options = sorted(result["Lapisan"].dropna().unique()) if "Lapisan" in result.columns else []
    lapisan_filter = col2.multiselect("Filter Lapisan", lapisan_options, key="mclub_lapisan_filter")

    view = result
    if query.strip():
        q = query.strip().lower()
        view = view[
            view["Cust"].astype(str).str.lower().str.contains(q, na=False)
            | view["Site"].astype(str).str.lower().str.contains(q, na=False)
        ]
    if lapisan_filter:
        view = view[view["Lapisan"].isin(lapisan_filter)]

    base_cols = ["Site", "Wil"]
    if category == "HOREKA":
        base_cols.append("Grup")
    base_cols += ["Cust", "Strata", "Lapisan", "RT2_25"]
    display_cols = [c for c in base_cols + list(METRIC_LABELS.keys()) if c in view.columns]

    st.caption(f"{len(view)} outlet ditemukan (dari {len(result)} total).")
    shown = view[display_cols].rename(columns=METRIC_LABELS)
    st.dataframe(shown, use_container_width=True, hide_index=True)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        shown.to_excel(writer, index=False, sheet_name="Outlet Lapisan")
    st.download_button(
        "Download Excel",
        data=buf.getvalue(),
        file_name=f"Outlet Lapisan {category}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
