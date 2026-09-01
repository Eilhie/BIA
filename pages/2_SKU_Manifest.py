"""
SKU MANIFEST
Single source of truth untuk 3 lapis coverage SKU yang sering ketuker: kode di
SKU_LIST (apa yang DICOBA disync) -> file yang benar-benar ada di DEST_DB (apa
yang BERHASIL disync) -> brand mapping aktif di transpose.py (apa yang IKUT
ditranspose ke laporan). Dihitung ulang tiap dibuka (file check-nya murah,
cuma Path.exists(), bukan buka isi file).
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
    "Setiap kode di `SKU_LIST` dicek 2 kali: **disync?** (file `OMSHAR ... .xls` ada di "
    "`DEST_DB`?) dan **terpetakan?** (dipakai suatu brand di `transpose.py`, ikut masuk "
    "laporan?). Kombinasi keduanya yang paling penting dicek adalah **terpetakan TAPI "
    "belum disync** -- brand yang mapping-nya sudah benar di kode, tapi file sumbernya "
    "belum/tidak ada, jadi datanya diam-diam kosong di laporan."
)
if btn_col.button("Refresh data"):
    # Data di-cache 10 menit (lihat ttl di build_sku_data) supaya tidak lambat kalau
    # dibuka berkali-kali -- tapi kalau baru selesai Sync/Transpose di halaman lain
    # dalam sesi yang sama, cache lama itu bisa telat update. Tombol ini paksa hitung
    # ulang sekarang juga tanpa perlu tunggu 10 menit atau restart app.
    build_sku_data.clear()
    st.rerun()

SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")
DEST_DB = Path(r"D:\DB OMSHAR\DB")

C_OK = "#4b7a5b"
C_OK_BG = "#e4efe6"
C_WARN = "#8a6d1f"
C_WARN_BG = "#f3ecd6"
C_BAD = "#a13327"
C_BAD_BG = "#f7e6e3"
C_MUTED = "#666666"
C_MUTED_BG = "#eaeaea"


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

    def build_group(category: str, list_dir: Path, file_map: dict):
        categories = []
        total = synced_total = mapped_total = missing_mapped_total = 0
        for txt in sorted(list_dir.glob("*.txt")):
            skus = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
            entries = []
            for sku in skus:
                brand = file_map.get(sku)
                synced = (DEST_DB / f"OMSHAR {category} {sku}.xls").exists()
                entries.append((sku, brand, synced))
                total += 1
                synced_total += synced
                mapped_total += bool(brand)
                missing_mapped_total += bool(brand) and not synced
            categories.append((txt.stem, entries))
        return categories, total, synced_total, mapped_total, missing_mapped_total

    umum_map = build_mapping(t.UMUM_FILE)
    horeka_map = build_mapping(t.HOREKA_FILE, t.HOREKA_KEG_FILE)

    umum_categories, umum_total, umum_synced, umum_mapped, umum_missing = build_group(
        "UMUM", SKU_LIST_DIR / "UMUM", umum_map)
    horeka_categories, horeka_total, horeka_synced, horeka_mapped, horeka_missing = build_group(
        "HOREKA", SKU_LIST_DIR / "HOREKA", horeka_map)

    return {
        "UMUM": {"categories": umum_categories, "total": umum_total, "synced": umum_synced,
                 "mapped": umum_mapped, "missing_mapped": umum_missing},
        "HOREKA": {"categories": horeka_categories, "total": horeka_total, "synced": horeka_synced,
                   "mapped": horeka_mapped, "missing_mapped": horeka_missing},
    }


def _status_pill(brand: str | None, synced: bool) -> str:
    if brand and not synced:
        # Kasus paling perlu diperhatikan: mapping-nya sudah benar, tapi file
        # sumbernya belum/tidak ada di DEST_DB -- brand ini diam-diam kosong
        # di laporan sampai file-nya benar-benar disync.
        return (f'<span style="background:{C_BAD_BG};color:{C_BAD};padding:2px 10px;'
                f'border-radius:999px;font-size:0.8rem;font-weight:600;">'
                f'{brand} -- FILE BELUM ADA</span>')
    if brand and synced:
        return (f'<span style="background:{C_OK_BG};color:{C_OK};padding:2px 10px;'
                f'border-radius:999px;font-size:0.8rem;font-weight:600;">{brand}</span>')
    if synced:
        return (f'<span style="background:{C_WARN_BG};color:{C_WARN};padding:2px 10px;'
                f'border-radius:999px;font-size:0.8rem;font-weight:600;">disync, belum terpetakan</span>')
    return (f'<span style="background:{C_MUTED_BG};color:{C_MUTED};padding:2px 10px;'
            f'border-radius:999px;font-size:0.8rem;font-weight:600;">belum disync & belum terpetakan</span>')


def build_channel_html(channel_data: dict, query: str, status_filter: str) -> str:
    q = query.strip().lower()
    html_parts = []
    for category, entries in channel_data["categories"]:
        filtered = []
        for sku, brand, synced in entries:
            if status_filter == "Terpetakan tapi belum disync" and not (brand and not synced):
                continue
            if status_filter == "Belum terpetakan" and brand:
                continue
            if status_filter == "Belum disync" and synced:
                continue
            if q and q not in sku.lower() and (not brand or q not in brand.lower()):
                continue
            filtered.append((sku, brand, synced))
        if not filtered:
            continue

        rows = ""
        for sku, brand, synced in filtered:
            pill = _status_pill(brand, synced)
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

total_missing_mapped = data["UMUM"]["missing_mapped"] + data["HOREKA"]["missing_mapped"]
if total_missing_mapped:
    st.error(
        f"{total_missing_mapped} kode SKU sudah terpetakan ke suatu brand tapi file-nya BELUM ADA "
        f"di `DEST_DB` -- brand terkait diam-diam kosong/kurang lengkap di laporan sampai Sync "
        f"berhasil menariknya. Cari status **\"FILE BELUM ADA\"** di bawah untuk lihat kodenya."
    )

s1, s2, s3 = st.columns(3)
s1.metric("UMUM: disync", f'{data["UMUM"]["synced"]}/{data["UMUM"]["total"]}')
s2.metric("UMUM: terpetakan", f'{data["UMUM"]["mapped"]}/{data["UMUM"]["total"]}')
s3.metric("UMUM: terpetakan tapi belum disync", data["UMUM"]["missing_mapped"])
s4, s5, s6 = st.columns(3)
s4.metric("HOREKA: disync", f'{data["HOREKA"]["synced"]}/{data["HOREKA"]["total"]}')
s5.metric("HOREKA: terpetakan", f'{data["HOREKA"]["mapped"]}/{data["HOREKA"]["total"]}')
s6.metric("HOREKA: terpetakan tapi belum disync", data["HOREKA"]["missing_mapped"])

col_q, col_c = st.columns([3, 1])
query = col_q.text_input("Cari kode SKU atau nama brand", placeholder="ketik untuk mencari...")
status_filter = col_c.selectbox(
    "Filter status",
    ["Semua", "Terpetakan tapi belum disync", "Belum terpetakan", "Belum disync"],
)

tab_umum, tab_horeka = st.tabs(["UMUM", "HOREKA"])
with tab_umum:
    st.markdown(build_channel_html(data["UMUM"], query, status_filter), unsafe_allow_html=True)
with tab_horeka:
    st.markdown(build_channel_html(data["HOREKA"], query, status_filter), unsafe_allow_html=True)
