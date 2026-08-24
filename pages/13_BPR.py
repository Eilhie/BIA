r"""
BPR (Buku Proposed Requirement / rekap harian NORM-STOK-DOI-Order)
Replika Python dari "BPR BIA DAILY TEMPLATE.xlsx" (sheet Rekap Per DEPO +
Rekap Per WILAYAH) -- selama ini dihitung manual lewat SUMIFS/AVERAGEIFS +
external link Excel yang harus di-relink manual tiap pagi (kalau lupa,
angkanya diam-diam basi). Halaman ini baca raw file harian LANGSUNG
(D:\Data BIA\2026\Daily Report\Kirim\...\BPR_BIA-<timestamp>.xls, dipilih
otomatis yang paling baru) dan hitung ulang dari nol tiap dibuka -- tidak
pernah kena masalah lupa relink.

Catatan: sheet 'Rekap Per WILAYAH' di template asli punya satu kolom
tambahan (F, tanpa header) yang formulanya salah-referensi (AVERAGEIFS
DOI per-Depo dari sheet lain, dicocokkan lewat NOMOR BARIS bukan nama
Wilayah/Depo -- artefak copy-paste, bukan data yang valid) -- SENGAJA
tidak direplikasi di sini.
"""

import pandas as pd
import streamlit as st

import auth
import bpr_pipeline as bp

BRAND_COLS = bp.BRAND_COLUMNS


@st.cache_data(show_spinner=False, ttl="10m")
def get_rekap() -> tuple[pd.DataFrame, pd.DataFrame, str] | None:
    path = bp.find_latest_raw()
    if path is None:
        return None
    raw = bp.load_raw(path)
    depo = bp.compute_rekap_depo(raw)
    wilayah = bp.compute_rekap_wilayah(raw, depo)
    return depo, wilayah, path.name


def _fmt_num(v, decimals=0) -> str:
    if pd.isna(v):
        return "-"
    return f"{v:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v) -> str:
    if pd.isna(v):
        return "-"
    return f"{v * 100:.1f}".replace(".", ",") + "%"


def _style_table(df: pd.DataFrame, index_cols: list[str]) -> pd.io.formats.style.Styler:
    disp = df.copy()
    for c in ["NORM"] + BRAND_COLS + ["TOTAL", "ACTUAL ORDER"]:
        if c in disp.columns:
            disp[c] = disp[c].apply(lambda v: _fmt_num(v, 0))
    if "STOK" in disp.columns:
        disp["STOK"] = disp["STOK"].apply(lambda v: _fmt_num(v, 2))
    if "DOI" in disp.columns:
        disp["DOI"] = disp["DOI"].apply(lambda v: _fmt_num(v, 1))
    if "%" in disp.columns:
        disp["%"] = disp["%"].apply(_fmt_pct)
    return disp


auth.require_level(5, page="BPR")
st.title("BPR")
st.caption(
    f"Sumber: file harian terbaru di bawah `{bp.KIRIM_DIR}` (dipilih otomatis dari timestamp di nama "
    "file) -- dihitung ulang langsung dari raw, tidak pernah kena masalah lupa relink external link "
    "seperti file kerja Excel-nya. Murni baca & tampilkan."
)

with st.spinner("Membaca & menghitung dari raw terbaru..."):
    result = get_rekap()

if result is None:
    st.error(f"Tidak ada file `BPR_BIA-<timestamp>.xls` ditemukan di bawah `{bp.KIRIM_DIR}`.")
    st.stop()

depo_df, wilayah_df, source_name = result
st.caption(f"File yang dibaca: `{source_name}`")

tab_depo, tab_wilayah = st.tabs(["Rekap Per Depo", "Rekap Per Wilayah"])

with tab_depo:
    st.caption(f"{len(depo_df) - 1} depo (baris terakhir = TOTAL semua depo).")
    st.dataframe(_style_table(depo_df, ["Wilayah", "Depo"]), use_container_width=True, hide_index=True)

with tab_wilayah:
    st.caption(
        "6 region (DKI/Banten/Bodebek/Jatim Utara/Jatim Selatan/Bali) x UMUM/HOREKA + baris subtotal "
        "REGION TOTAL -- cakupan sama seperti template asli, bukan seluruh wilayah perusahaan."
    )
    st.dataframe(_style_table(wilayah_df, ["Wilayah"]), use_container_width=True, hide_index=True)
