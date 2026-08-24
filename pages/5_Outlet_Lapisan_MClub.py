"""
OUTLET LAPISAN (MCLUB)
Otomatisasi klasifikasi tier outlet Gold/Platinum/MCLUB + analisis kompetitif
(OMS LOSS, INDUSTRI, pangsa pasar) dari file RAW yang diterima dari divisi lain.
Menggantikan proses manual maintain file kerja 55MB/13MB + REKAP + PDF.
"""

import io

import pandas as pd
import streamlit as st

import auth
import mclub_pipeline as mp

auth.require_level(4, page="Outlet Lapisan (MClub)")
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

# Kolom rasio (0.0-1.0-an) yang di file kerja Excel-nya diformat cell sebagai '0%'
# (bilangan bulat, tanpa desimal) -- dicek langsung pakai openpyxl di KEDUA channel
# (UMUM & HOREKA), bukan tebakan, dan ternyata sama persis di keduanya.
PCT_COLS = ["PCT_SMT1_VS_SMT2", "PCT_SMT1_VS_RT25", "PCT_BIR_VS_MUSUH", "PCT_BIR_VS_INDUSTRI"]

# Kolom angka (KRT) -- file kerja aslinya pakai format akuntansi 1 desimal
# (`#,##0.0`), tapi user minta 2 desimal di sini secara eksplisit.
NUM_COLS = ["RT2_25", "SMT2_25", "SMT1_26", "OMS_LOSS", "TOTAL_MUSUH", "INDUSTRI"]


def _fmt_num(v) -> str:
    if pd.isna(v):
        return "-"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct_tier_css(v) -> str:
    """Skema warna PERSIS sama dengan conditional formatting asli di file Excel
    kerja-nya -- dicek langsung lewat dxf styles openpyxl (bukan tebakan), dan
    identik di ketiga pasangan kolom % (SMT1 vs SMT2/RT25, BIR vs Musuh/Industri)
    di KEDUA channel: <=0% polos (theme putih di file asli), 0-100% hijau,
    100-115% kuning, 115-130% oranye, 130-150% merah, >=150% ungu."""
    if pd.isna(v) or v <= 0:
        return ""
    if v <= 1:
        return "background-color: #00FF00; color: #000; font-weight: bold;"
    if v <= 1.15:
        return "background-color: #FFFF00; color: #000; font-weight: bold;"
    if v <= 1.3:
        return "background-color: #FFC000; color: #000; font-weight: bold;"
    if v <= 1.5:
        return "background-color: #FF0000; color: #fff; font-weight: bold;"
    return "background-color: #6600CC; color: #fff;"

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

    current_month = mp.current_month_key()

    base_cols = ["Site", "Wil"]
    if category == "HOREKA":
        base_cols.append("Grup")
    base_cols += ["Cust", "Strata", "Lapisan", "RT2_25"]
    if current_month in view.columns:
        base_cols.append(current_month)
        st.caption(f"Kolom **{current_month}** = omset bulan berjalan, biasanya belum lengkap sampai RAW berikutnya masuk.")
    else:
        st.info(f"Kolom bulan berjalan ({current_month}) belum ada di archive -- upload RAW terbaru untuk menampilkannya.")
    display_cols = [c for c in base_cols + list(METRIC_LABELS.keys()) if c in view.columns]

    st.caption(f"{len(view)} outlet ditemukan (dari {len(result)} total).")
    shown = view[display_cols].copy()

    # Simpan nilai % MENTAH (sebelum diformat jadi string) dulu, dikunci ke label
    # SETELAH rename -- dipakai nanti buat conditional formatting warnanya, karena
    # begitu jadi string "55%" nilai aslinya sudah tidak bisa dipakai untuk
    # menentukan tier warna.
    raw_pct = {METRIC_LABELS[col]: shown[col] for col in PCT_COLS if col in shown.columns}

    # Format persen SAMA PERSIS seperti format cell di file kerja Excel-nya:
    # cek langsung (openpyxl, number_format cell) di kedua channel (UMUM & HOREKA)
    # -- keduanya pakai '0%' (bilangan bulat, tanpa desimal), bukan tebakan.
    for col in PCT_COLS:
        if col in shown.columns:
            shown[col] = shown[col].apply(lambda v: f"{v * 100:.0f}%" if pd.notna(v) else "-")

    # Angka KRT dibulatkan 2 desimal, format Indonesia (koma sbg desimal).
    for col in NUM_COLS + [current_month]:
        if col in shown.columns:
            shown[col] = shown[col].apply(_fmt_num)

    shown = shown.rename(columns=METRIC_LABELS)

    def _style_pct_col(col_series):
        raw = raw_pct.get(col_series.name)
        if raw is None:
            return [""] * len(col_series)
        return [_pct_tier_css(raw.loc[idx]) for idx in col_series.index]

    try:
        st.dataframe(
            shown.style.apply(_style_pct_col, subset=list(raw_pct.keys()), axis=0),
            use_container_width=True, hide_index=True,
        )
    except Exception:
        # fallback kalau styling tidak didukung versi Streamlit ini
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
