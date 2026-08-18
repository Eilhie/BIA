"""
DETAIL SKU BRAND BESAR
Laporan detail per outlet untuk brand-brand besar (PALS, PLAG, PPIL, PRL, WBR,
SINGARAJA, SOMAEK) -- dipecah sampai ke level varian SKU individual (botol/
kaleng/pint/keg dsb), bukan cuma total brand seperti di Omset Seeker. Tabelnya
sendiri format PERSIS Omset Seeker (2025 + RT2 25 | BRAND | 2026 + RT2 26,
warna sama) -- satu baris per varian SKU, bukan per brand gabungan.

PENTING: sebagian besar kode varian di sini TIDAK pernah tersentuh transpose.py
(itu cuma proses SKU yang terdaftar di UMUM_FILE/HOREKA_FILE, sebagian besar
varian legacy/kemasan lain di sini bukan bagian dari situ) -- artinya jalur
cepat SKU_RAW tidak berlaku, dan tiap SKU yang belum ke-cache butuh baca .xls
mentah langsung (~20-25 detik/SKU). Diukur nyata: dari 7 brand ini, cuma
~15-20% kode yang punya cache cepat -- kalau SEMUA ditampilkan sekaligus bisa
~20+ menit. Makanya defaultnya cuma yang sudah cepat, sisanya opt-in manual.
"""

import io
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import omset_seeker as os_
import sku_lookup as sl
from render_outlet_image import build_html_table, build_row_cells

auth.require_level(5, page="Detail SKU Brand Besar")
st.title("Detail SKU Brand Besar")
st.caption(
    "Pecahan varian SKU individual untuk brand-brand besar -- PALS, PLAG, PPIL, "
    "PRL, WBR, SINGARAJA, SOMAEK -- format tabel persis Omset Seeker (2025 + RT2 25 "
    "| BRAND | 2026 + RT2 26), tapi satu baris per VARIAN SKU, bukan per total brand."
)

# Grup SKU_LIST yang jadi sumber daftar varian tiap brand besar -- dibaca
# LANGSUNG dari file SKU_LIST (bukan hardcode daftar SKU-nya), jadi otomatis
# ikut kalau ada perubahan lewat halaman Atur SKU Sync.
BRAND_GROUPS = {
    "PALS (Prost Alster)": "PROST ALSTER",
    "PLAG (Prost Lager)": "PROST LAGER",
    "PPIL (Prost Pilsener)": "PROST PILSENER",
    "PRL (Prost Rajawali)": "PROST RAJAWALI",
    "WBR (Konig Weissbier)": "KONIG",
    "SINGARAJA": "SINGARAJA",
    "SOMAEK": "BAE SOMAEK",
}

SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")


def _load_group_skus(category: str, group_file: str) -> list[str]:
    path = SKU_LIST_DIR / category / f"{group_file}.txt"
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]


def _all_skus(category: str) -> list[tuple[str, str]]:
    """(label_brand, kode_sku) buat semua varian di 7 grup, urut sesuai BRAND_GROUPS."""
    out = []
    for label, group_file in BRAND_GROUPS.items():
        for sku in _load_group_skus(category, group_file):
            out.append((label, sku))
    return out


def _is_fast(category: str, sku: str) -> bool:
    """True kalau SKU ini sudah punya cache SKU_RAW LENGKAP (2025+2026, dari
    Transpose versi terbaru) -- kalau tidak, get_sku_trend() jatuh ke baca .xls
    mentah (~20-25 detik). File cache format LAMA (cuma 2026, dari sebelum SKU_RAW
    diperluas) SENGAJA dihitung 'belum cepat' di sini -- load_sku_raw() sendiri
    juga akan fallback ke raw kalau ketemu cache format lama, jadi estimasi waktu
    di halaman ini tetap akurat, bukan optimis palsu."""
    path = sl._sku_raw_cache_path(category, sku)
    if not path.exists():
        return False
    try:
        cols = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns
        return all(m in cols for m in sl.MONTH_LABELS_ALL)
    except Exception:
        return False


@st.cache_data(show_spinner=False, ttl="10m")
def get_outlet_index(omshar_type: str) -> pd.DataFrame:
    return os_.build_outlet_index(omshar_type)


category = st.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="detail_cat")

query = st.text_input("Cari outlet (nama/kode)", key="detail_query", placeholder="ketik untuk mencari...")
site = None
if query.strip():
    with st.spinner(f"Memuat daftar outlet {category}..."):
        idx = get_outlet_index(category)
    q = query.strip().lower()
    matches = idx[
        idx["Outlet"].str.lower().str.contains(q, na=False, regex=False)
        | idx["Site"].str.lower().str.contains(q, na=False, regex=False)
    ].head(30)
    if matches.empty:
        st.caption("Tidak ada outlet yang cocok.")
    else:
        labels = {f"{r['Outlet']} ({r['Site']})": r["Site"] for _, r in matches.iterrows()}
        # index=None -- SENGAJA tidak auto-pilih opsi pertama. selectbox default
        # Streamlit otomatis "memilih" options[0] begitu dirender, yang tanpa
        # sadar langsung memicu loop SKU (lambat) di bawah PADA SAAT SEARCH SAJA,
        # sebelum user benar-benar memilih apa pun -- ini penyebab nyata halaman
        # ini pernah macet >2 menit cuma dari mengetik kata pencarian.
        picked = st.selectbox("Pilih outlet", list(labels.keys()), index=None, key="detail_pick")
        site = labels[picked] if picked else None

if site:
    all_skus = _all_skus(category)
    fast_skus = [(label, sku) for label, sku in all_skus if _is_fast(category, sku)]
    slow_skus = [(label, sku) for label, sku in all_skus if not _is_fast(category, sku)]

    outlet_idx = get_outlet_index(category).set_index("Site")
    outlet_name = outlet_idx["Outlet"].get(site, site)
    st.subheader(f"{site} -- {outlet_name}")

    if slow_skus:
        est_min = len(slow_skus) * 22 / 60
        st.caption(
            f"{len(fast_skus)}/{len(all_skus)} varian SKU sudah punya cache cepat (langsung tampil di "
            f"bawah). {len(slow_skus)} varian lain belum pernah di-Transpose (atau cache-nya masih "
            f"format lama, belum ikut 2025) -- baca langsung dari .xls mentah kira-kira "
            f"**~{est_min:.0f} menit** kalau disertakan (centang di bawah)."
        )
        include_slow = st.checkbox(
            f"Sertakan {len(slow_skus)} varian yang belum ke-cache (lambat, ~{est_min:.0f} menit)",
            value=False, key="detail_include_slow",
        )
    else:
        include_slow = True

    todo = fast_skus + (slow_skus if include_slow else [])

    # cutoff_parts dari kategori ini -- bulan 2026 yang sudah genap tutup buku,
    # persis logika RT2 26 di Omset Seeker (build_report_rows()), supaya rata-rata
    # RT2 26 di sini tidak ikut kebagi bulan yang belum jalan sama sekali.
    cutoff_parts = os_.get_cutoff_parts(omshar_type=category)
    months_26_closed = (cutoff_parts[1] - 1) if cutoff_parts else 12

    trends = {}
    progress = st.progress(0.0, text=f"Memuat 0/{len(todo)} varian SKU...") if slow_skus and include_slow else None
    t0 = time.time()
    for i, (label, sku) in enumerate(todo):
        trends[(label, sku)] = sl.get_sku_trend(category, sku, site)
        if progress is not None:
            progress.progress((i + 1) / len(todo), text=f"Memuat {i + 1}/{len(todo)} varian SKU...")
    if progress is not None:
        progress.empty()
        st.caption(f"Selesai dalam {time.time() - t0:.0f} detik.")

    if not trends:
        st.info("Tidak ada data SKU untuk brand-brand ini di kategori ini.")
    else:
        only_active = st.checkbox("Tampilkan yang ada penjualan saja (Total > 0)", value=True, key="detail_only_active")

        row_cells = []
        excel_rows = []
        for (label, sku), trend in trends.items():
            total = sum(trend.values())
            if only_active and total <= 0:
                continue
            vals_25, rt2_25, vals_26, rt2_26 = build_row_cells(trend, months_26_closed)
            row_label = f"{label} -- {sku}"
            row_cells.append((vals_25, rt2_25, row_label, vals_26, rt2_26, "normal"))
            excel_rows.append({"Brand": label, "SKU": sku, **trend, "Total": total})

        st.caption(
            f"{len(row_cells)} varian SKU ditampilkan (dari {len(trends)} yang dimuat, "
            f"{len(all_skus)} total di 7 brand ini)."
        )

        if not row_cells:
            st.info("Tidak ada varian dengan penjualan (Total > 0) untuk ditampilkan -- coba matikan filter di atas.")
        else:
            st.markdown(build_html_table(row_cells), unsafe_allow_html=True)

            buf = io.BytesIO()
            excel_df = pd.DataFrame(excel_rows)
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                excel_df.to_excel(writer, index=False, sheet_name="Detail SKU")
            st.download_button(
                "Download Excel",
                data=buf.getvalue(),
                file_name=f"Detail SKU Brand Besar - {site}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
