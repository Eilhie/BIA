r"""
BPR (Buku Proposed Requirement / rekap harian NORM-STOK-DOI-Order)
Replika Python dari "BPR BIA DAILY TEMPLATE.xlsx" (sheet Rekap Per DEPO +
Rekap Per WILAYAH) -- selama ini dihitung manual lewat SUMIFS/AVERAGEIFS +
external link Excel yang harus di-relink manual tiap pagi (kalau lupa,
angkanya diam-diam basi). Halaman ini baca raw file harian LANGSUNG dari
Google Drive (G:\My Drive\BPR BIA\BPR_BIA-<timestamp>.7z, sumber ASLI --
masuk otomatis tiap ~07:00 termasuk weekend, dipilih otomatis yang paling
baru), fallback ke arsip lokal D:\Data BIA\...\Kirim\ (.xls) kalau G: tidak
ke-mount. Folder lokal ternyata cuma salinan yang diekstrak MANUAL oleh
seseorang dari Google Drive -- kadang skip weekend/telat, jadi bukan
sumber utama lagi. Dihitung ulang dari nol tiap dibuka -- tidak pernah kena
masalah lupa relink.

Tampilan + warna kolom (DATA kuning, PROPOSED ORDER hijau/oranye, TOTAL
merah, ACTUAL ORDER/% gelap) meniru PERSIS template Excel asli -- lihat
render_bpr.py. Export Excel & PDF juga sama persis warnanya.

Kolom "TOTAL <tanggal>" (perbandingan TOTAL hari kerja sebelumnya) juga
direplikasi -- tapi dihitung ULANG dari raw file historis LANGSUNG (lihat
bp.find_previous_raw()), bukan lewat external link manual seperti template
asli yang terbukti sering telat beberapa hari.

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
import render_bpr as rb


@st.cache_data(show_spinner=False, ttl="10m")
def get_rekap() -> tuple[pd.DataFrame, pd.DataFrame, str] | None:
    path = bp.find_latest_raw()
    if path is None:
        return None
    raw = bp.load_raw(path)
    depo = bp.compute_rekap_depo(raw)
    wilayah = bp.compute_rekap_wilayah(raw, depo)

    prev_path = bp.find_previous_raw(path)
    if prev_path is not None:
        prev_raw = bp.load_raw(prev_path)
        prev_depo = bp.compute_rekap_depo(prev_raw)
        prev_wilayah = bp.compute_rekap_wilayah(prev_raw, prev_depo)
        label = bp.previous_total_label(prev_path)
        depo = bp.add_previous_total(depo, ["Wilayah", "Depo"], prev_depo, label)
        wilayah = bp.add_previous_total(wilayah, ["Wilayah"], prev_wilayah, label)

    return depo, wilayah, path.name


auth.require_level(4, page="BPR")
st.title("BPR")
st.caption(
    f"Sumber: Google Drive `{bp.GDRIVE_BPR_DIR}` (fallback ke arsip lokal `{bp.KIRIM_DIR}` kalau G: "
    "tidak ke-mount) -- dihitung ulang langsung dari raw, tidak pernah kena masalah lupa relink "
    "external link seperti file kerja Excel-nya. Murni baca & tampilkan."
)

with st.spinner("Membaca & menghitung dari raw terbaru..."):
    result = get_rekap()

if result is None:
    st.error(f"Tidak ada file `BPR_BIA-<timestamp>` ditemukan di `{bp.GDRIVE_BPR_DIR}` maupun `{bp.KIRIM_DIR}`.")
    st.stop()

depo_df, wilayah_df, source_name = result
update_label = rb.format_update_label(source_name)
st.caption(f"File yang dibaca: `{source_name}` -- {update_label}")

source_stem = source_name.rsplit(".", 1)[0]
col_xlsx, col_pdf = st.columns(2)
with col_xlsx:
    st.download_button(
        "Download Excel",
        data=rb.build_excel_bytes(depo_df, wilayah_df, update_label),
        file_name=f"BPR BIA - {source_stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with col_pdf:
    if rb.MATPLOTLIB_AVAILABLE:
        st.download_button(
            "Download PDF",
            data=rb.build_pdf_bytes(depo_df, wilayah_df, update_label),
            file_name=f"BPR BIA - {source_stem}.pdf",
            mime="application/pdf",
        )
    else:
        st.caption("PDF tidak tersedia -- matplotlib gagal dimuat.")

tab_depo, tab_wilayah = st.tabs(["Rekap Per Depo", "Rekap Per Wilayah"])

with tab_depo:
    st.caption(f"{len(depo_df) - 1} depo (baris terakhir = TOTAL semua depo).")
    st.markdown(rb.build_html_table(depo_df, "Rekap Per Depo", update_label), unsafe_allow_html=True)

with tab_wilayah:
    st.caption(
        "6 region (DKI/Banten/Bodebek/Jatim Utara/Jatim Selatan/Bali) x UMUM/HOREKA + baris subtotal "
        "REGION TOTAL -- cakupan sama seperti template asli, bukan seluruh wilayah perusahaan."
    )
    st.markdown(rb.build_html_table(wilayah_df, "Rekap Per Wilayah", update_label), unsafe_allow_html=True)
