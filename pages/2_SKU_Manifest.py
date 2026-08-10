"""
SKU MANIFEST
Audit coverage SKU (dari SKU_LIST) terhadap brand mapping aktif di transpose.py --
versi live dari artifact statis yang dibuat sebelumnya, dihitung ulang tiap dibuka.
"""

import sys
from pathlib import Path

import streamlit as st

import auth

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omset_pipeline"))
import transpose as t  # noqa: E402

auth.require_level(5, page="SKU Manifest")
st.title("SKU Manifest")
cap_col, btn_col = st.columns([5, 1])
cap_col.caption(
    "Semua SKU dari `SKU_LIST` UMUM/HOREKA, dicek terhadap brand mapping aktif di "
    "`transpose.py`. **Terpetakan** = SKU ini masuk ke suatu brand dan ikut ditranspose. "
    "**Belum terpetakan** = disync dari server tapi tidak dipakai di laporan mana pun."
)
if btn_col.button("Refresh data"):
    # Data di-cache 10 menit (lihat ttl di build_sku_data) supaya tidak lambat kalau
    # dibuka berkali-kali -- tapi kalau baru selesai Sync/Transpose di halaman lain
    # dalam sesi yang sama, cache lama itu bisa telat update. Tombol ini paksa hitung
    # ulang sekarang juga tanpa perlu tunggu 10 menit atau restart app.
    build_sku_data.clear()
    st.rerun()

SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")

C_MAPPED = "#4b7a5b"
C_MAPPED_BG = "#e4efe6"
C_UNMAPPED = "#a13327"
C_UNMAPPED_BG = "#f7e6e3"


@st.cache_data(show_spinner=False, ttl="10m")
def build_sku_data():
    def build_mapping(file_map, extra_map=None):
        m = {}
        for brand, files in file_map.items():
            for f in files:
                m[f] = brand
        if extra_map:
            for brand, files in extra_map.items():
                for f in files:
                    m[f] = brand
        return m

    def build_group(list_dir: Path, file_map: dict):
        categories = []
        total = mapped_total = 0
        for txt in sorted(list_dir.glob("*.txt")):
            skus = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
            entries = [(sku, file_map.get(sku)) for sku in skus]
            categories.append((txt.stem, entries))
            total += len(entries)
            mapped_total += sum(1 for _, brand in entries if brand)
        return categories, total, mapped_total

    umum_map = build_mapping(t.UMUM_FILE)
    horeka_map = build_mapping(t.HOREKA_FILE, t.HOREKA_KEG_FILE)

    umum_categories, umum_total, umum_mapped = build_group(SKU_LIST_DIR / "UMUM", umum_map)
    horeka_categories, horeka_total, horeka_mapped = build_group(SKU_LIST_DIR / "HOREKA", horeka_map)

    return {
        "UMUM": {"categories": umum_categories, "total": umum_total, "mapped": umum_mapped},
        "HOREKA": {"categories": horeka_categories, "total": horeka_total, "mapped": horeka_mapped},
    }


def build_channel_html(channel_data: dict, query: str, unmapped_only: bool) -> str:
    q = query.strip().lower()
    html_parts = []
    for category, entries in channel_data["categories"]:
        filtered = []
        for sku, brand in entries:
            if unmapped_only and brand:
                continue
            if q and q not in sku.lower() and (not brand or q not in brand.lower()):
                continue
            filtered.append((sku, brand))
        if not filtered:
            continue

        rows = ""
        for sku, brand in filtered:
            if brand:
                pill = f'<span style="background:{C_MAPPED_BG};color:{C_MAPPED};padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;">{brand}</span>'
            else:
                pill = f'<span style="background:{C_UNMAPPED_BG};color:{C_UNMAPPED};padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;">belum terpetakan</span>'
            rows += (
                f'<tr><td style="padding:5px 10px;font-family:monospace;border-top:1px solid #444;">{sku}</td>'
                f'<td style="padding:5px 10px;text-align:right;border-top:1px solid #444;">{pill}</td></tr>'
            )

        html_parts.append(f"""
        <div style="border:1px solid #555;border-radius:8px;margin-bottom:12px;overflow:hidden;">
          <div style="padding:8px 12px;background:rgba(128,128,128,0.15);font-weight:600;font-size:0.9rem;">
            {category} <span style="color:#888;font-weight:400;font-size:0.8rem;">({len(filtered)}/{len(entries)})</span>
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">{rows}</table>
        </div>
        """)

    if not html_parts:
        return "<p style='color:#888;'>Tidak ada SKU yang cocok.</p>"
    return "".join(html_parts)


data = build_sku_data()

s1, s2, s3, s4 = st.columns(4)
s1.metric("UMUM total", data["UMUM"]["total"])
s2.metric("UMUM terpetakan", data["UMUM"]["mapped"])
s3.metric("HOREKA total", data["HOREKA"]["total"])
s4.metric("HOREKA terpetakan", data["HOREKA"]["mapped"])

col_q, col_c = st.columns([3, 1])
query = col_q.text_input("Cari kode SKU atau nama brand", placeholder="ketik untuk mencari...")
unmapped_only = col_c.checkbox("Belum terpetakan saja", value=False)

tab_umum, tab_horeka = st.tabs(["UMUM", "HOREKA"])
with tab_umum:
    st.markdown(build_channel_html(data["UMUM"], query, unmapped_only), unsafe_allow_html=True)
with tab_horeka:
    st.markdown(build_channel_html(data["HOREKA"], query, unmapped_only), unsafe_allow_html=True)
