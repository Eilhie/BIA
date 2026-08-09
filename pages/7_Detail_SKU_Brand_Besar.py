"""
DETAIL SKU BRAND BESAR
Laporan detail per outlet untuk brand-brand besar (PALS, PLAG, PPIL, PRL, WBR,
SINGARAJA, SOMAEK) -- dipecah sampai ke level varian SKU individual (botol/
kaleng/pint/keg dsb), bukan cuma total brand seperti di Omset Seeker.

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

auth.require_level(5, page="Detail SKU Brand Besar")
st.title("Detail SKU Brand Besar")
st.caption(
    "Pecahan varian SKU individual untuk brand-brand besar -- PALS, PLAG, PPIL, "
    "PRL, WBR, SINGARAJA, SOMAEK -- trend Jan-Des 2026 per outlet. Laporan Omset "
    "Seeker yang biasa cuma tampilkan total brand-nya, bukan pecahan tiap varian."
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
    """True kalau SKU ini sudah punya cache SKU_RAW (dari Transpose) -- kalau
    tidak, get_sku_trend() bakal jatuh ke baca .xls mentah (~20-25 detik)."""
    return sl._sku_raw_cache_path(category, sku).exists()


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
            f"bawah). {len(slow_skus)} varian lain belum pernah di-Transpose -- baca langsung dari "
            f".xls mentah kira-kira **~{est_min:.0f} menit** kalau disertakan (centang di bawah)."
        )
        include_slow = st.checkbox(
            f"Sertakan {len(slow_skus)} varian yang belum ke-cache (lambat, ~{est_min:.0f} menit)",
            value=False, key="detail_include_slow",
        )
    else:
        include_slow = True

    todo = fast_skus + (slow_skus if include_slow else [])

    rows = []
    progress = st.progress(0.0, text=f"Memuat 0/{len(todo)} varian SKU...") if slow_skus and include_slow else None
    t0 = time.time()
    for i, (label, sku) in enumerate(todo):
        trend = sl.get_sku_trend(category, sku, site)
        total = sum(trend.values())
        rows.append({"Brand": label, "SKU": sku, **trend, "Total": total})
        if progress is not None:
            progress.progress((i + 1) / len(todo), text=f"Memuat {i + 1}/{len(todo)} varian SKU...")
    if progress is not None:
        progress.empty()
        st.caption(f"Selesai dalam {time.time() - t0:.0f} detik.")

    if not rows:
        st.info("Tidak ada data SKU untuk brand-brand ini di kategori ini.")
    else:
        df = pd.DataFrame(rows)
        only_active = st.checkbox("Tampilkan yang ada penjualan saja (Total > 0)", value=True, key="detail_only_active")
        view = df[df["Total"] > 0] if only_active else df
        st.caption(f"{len(view)} varian SKU ditampilkan (dari {len(df)} yang dimuat, {len(all_skus)} total di 7 brand ini).")
        st.dataframe(view, use_container_width=True, hide_index=True)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            view.to_excel(writer, index=False, sheet_name="Detail SKU")
        st.download_button(
            "Download Excel",
            data=buf.getvalue(),
            file_name=f"Detail SKU Brand Besar - {site}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
