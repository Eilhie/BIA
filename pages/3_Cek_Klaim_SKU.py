"""
CEK KLAIM SKU
Cek QTY (KRT) per VARIAN SKU individu per outlet, trend Jan-Des 2026 -- dipakai buat
verifikasi klaim dari surat usulan yang dihitung QTY x promo per SKU spesifik (bukan
total per brand seperti Omset Seeker). Perhitungan promo/rupiah dilakukan manual di
luar tool ini -- tool ini cuma menyediakan angka QTY-nya.
"""

from io import BytesIO

import pandas as pd
import streamlit as st

import omset_seeker
import sku_lookup

st.set_page_config(page_title="Cek Klaim SKU", layout="wide")
st.title("Cek Klaim SKU")
st.caption(
    "QTY (KRT) per varian SKU individu, per outlet, trend Jan-Des 2026 -- dibaca "
    "langsung dari file OMSHAR mentah per SKU (bukan dari hasil transpose brand yang "
    "sudah digabung). Untuk cek klaim QTY x promo per SKU; hitung nilai klaimnya "
    "dilakukan manual di luar tool ini."
)

MONTHS = sku_lookup.MONTH_LABELS_2026


@st.cache_data(show_spinner=False, ttl="10m")
def get_outlet_index(omshar_type: str) -> pd.DataFrame:
    return omset_seeker.build_outlet_index(omshar_type)


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Klaim SKU")
    return buf.getvalue()


tab_manual, tab_batch = st.tabs(["Cari Manual", "Cek Batch"])

# ── TAB 1: CARI MANUAL ─────────────────────────────────────────────────────────

with tab_manual:
    col_cat, col_brand, col_sku = st.columns(3)
    category = col_cat.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="manual_cat")

    catalog = sku_lookup.get_sku_catalog(category)
    brand = col_brand.selectbox("Brand", sorted(catalog.keys()), key="manual_brand")
    sku_options = catalog.get(brand, [])
    sku_name = col_sku.selectbox("Varian SKU", sku_options, key="manual_sku")

    st.divider()
    query = st.text_input("Cari outlet (nama/kode)", key="manual_outlet_query", placeholder="ketik untuk mencari...")

    selected_sites: list[str] = []
    if query.strip():
        with st.spinner(f"Memuat daftar outlet {category}..."):
            outlets = get_outlet_index(category)
        q = query.strip().lower()
        matches = outlets[
            outlets["Outlet"].str.lower().str.contains(q, na=False, regex=False)
            | outlets["Site"].str.lower().str.contains(q, na=False, regex=False)
        ].head(50)
        if matches.empty:
            st.caption("Tidak ada outlet yang cocok.")
        else:
            labels = {
                f"{row['Outlet']} ({row['Site']})": row["Site"]
                for _, row in matches.iterrows()
            }
            picked_labels = st.multiselect("Pilih outlet (bisa lebih dari satu)", list(labels.keys()))
            selected_sites = [labels[lbl] for lbl in picked_labels]

    if selected_sites:
        with st.spinner(f"Mengambil data {sku_name}..."):
            outlets_idx = get_outlet_index(category).set_index("Site")
            rows = []
            for site in selected_sites:
                trend = sku_lookup.get_sku_trend(category, sku_name, site)
                name = outlets_idx["Outlet"].get(site, "(tidak diketahui)")
                row = {"Site": site, "Outlet": name, **trend}
                row["Total"] = sum(trend.values())
                rows.append(row)
            result_df = pd.DataFrame(rows)

        st.subheader(f"{sku_name} ({brand}) -- trend {MONTHS[0]} s/d {MONTHS[-1]}")
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Excel",
            data=_to_excel_bytes(result_df),
            file_name=f"Klaim {sku_name} {category}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.caption("Cari lalu pilih minimal satu outlet untuk lihat trend QTY-nya.")

# ── TAB 2: CEK BATCH ───────────────────────────────────────────────────────────

with tab_batch:
    st.caption(
        "Upload daftar (Site, SKU) dari surat usulan -- QTY per bulan diisi otomatis. "
        "Nama SKU harus persis sama dengan salah satu varian di daftar brand (lihat "
        "tab Cari Manual untuk daftar nama yang valid)."
    )

    batch_category = st.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="batch_cat")

    template_df = pd.DataFrame({"Site": ["contoh: 0815-02000166"], "SKU": ["contoh: ABIDIN"]})
    st.download_button(
        "Download template",
        data=_to_excel_bytes(template_df),
        file_name="Template Cek Klaim SKU.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    uploaded = st.file_uploader("Upload daftar (.xlsx atau .csv)", type=["xlsx", "csv"], key="batch_upload")

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                batch_in = pd.read_csv(uploaded, dtype=str)
            else:
                batch_in = pd.read_excel(uploaded, dtype=str)
        except Exception as e:
            st.error(f"Gagal baca file: {e}")
            batch_in = None

        if batch_in is not None:
            missing_cols = {"Site", "SKU"} - set(batch_in.columns)
            if missing_cols:
                st.error(f"Kolom wajib tidak ada: {', '.join(sorted(missing_cols))}. Cek template di atas.")
            else:
                batch_in = batch_in.dropna(subset=["Site", "SKU"]).copy()
                batch_in["Site"] = batch_in["Site"].str.strip()
                batch_in["SKU"] = batch_in["SKU"].str.strip()

                valid_skus = {s for files in sku_lookup.get_sku_catalog(batch_category).values() for s in files}
                unknown = sorted(set(batch_in["SKU"]) - valid_skus)
                if unknown:
                    st.warning(
                        f"{len(unknown)} nama SKU tidak dikenali (dilewati, hasilnya 0): "
                        + ", ".join(unknown)
                    )

                with st.spinner(f"Menghitung {len(batch_in)} baris..."):
                    outlets_idx = get_outlet_index(batch_category).set_index("Site")
                    rows = []
                    for _, r in batch_in.iterrows():
                        site, sku = r["Site"], r["SKU"]
                        trend = sku_lookup.get_sku_trend(batch_category, sku, site)
                        name = outlets_idx["Outlet"].get(site, "(site tidak ditemukan)")
                        row = {"Site": site, "Outlet": name, "SKU": sku, **trend}
                        row["Total"] = sum(trend.values())
                        rows.append(row)
                    result_df = pd.DataFrame(rows)

                st.dataframe(result_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download hasil (Excel)",
                    data=_to_excel_bytes(result_df),
                    file_name=f"Hasil Cek Klaim {batch_category}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
