"""
ATUR GABUNGAN HOREKA
Definisikan grup toko HOREKA yang mau digabung jadi satu identitas laporan --
sama seperti Toko Gabungan UMUM, tapi UMUM sumbernya file Excel bulanan dari
divisi lain, sementara HOREKA tidak punya proses/file semacam itu sama sekali,
jadi didefinisikan manual di sini. Data disimpan lokal (CSV), independen
total dari sumber UMUM -- lihat omset_seeker.HOREKA_GABUNGAN_PATH.
"""

import pandas as pd
import streamlit as st

import auth
import database as db
import omset_seeker as os_

current = auth.require_level(5, page="Atur Gabungan HOREKA")
st.title("Atur Gabungan HOREKA")
st.caption(
    "Gabungkan beberapa site HOREKA jadi satu identitas laporan (mis. beberapa outlet "
    "di lokasi yang sama) -- sekali dibuat, kode gabungannya otomatis muncul di "
    "pencarian Omset Seeker grup HOREKA dan angkanya dijumlah dari semua toko anaknya, "
    "persis seperti Toko Gabungan UMUM."
)


def _load_rows() -> pd.DataFrame:
    if os_.HOREKA_GABUNGAN_PATH.exists():
        return pd.read_csv(os_.HOREKA_GABUNGAN_PATH, dtype=str, encoding="utf-8-sig")
    return pd.DataFrame(columns=["Wilayah", "Site", "Outlet", "Group"])


def _save_rows(df: pd.DataFrame) -> None:
    os_.HOREKA_GABUNGAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(os_.HOREKA_GABUNGAN_PATH, index=False, encoding="utf-8-sig")
    os_.load_horeka_gabungan_map.cache_clear()
    os_.load_gabungan_map.cache_clear()


@st.cache_data(show_spinner=False, ttl="10m")
def _horeka_outlet_names() -> dict:
    idx = os_.build_outlet_index("HOREKA")
    return idx.set_index("Site")["Outlet"].to_dict()


rows_df = _load_rows()
groups = sorted(rows_df["Group"].dropna().unique().tolist()) if not rows_df.empty else []

st.divider()
st.subheader(f"Grup yang sudah ada ({len(groups)})")

if not groups:
    st.info("Belum ada grup gabungan HOREKA.")
else:
    outlet_names = _horeka_outlet_names()
    for g in groups:
        g_rows = rows_df[rows_df["Group"] == g]
        wilayah = g_rows["Wilayah"].iloc[0] if not g_rows.empty else "-"
        with st.expander(f"{g} -- {wilayah} -- {len(g_rows)} toko"):
            for _, r in g_rows.iterrows():
                name = outlet_names.get(r["Site"], "(tidak ditemukan di data HOREKA)")
                st.caption(f"`{r['Site']}` -- {name}")
            if st.button("Hapus grup ini", key=f"del_gab_{g}"):
                _save_rows(rows_df[rows_df["Group"] != g])
                db.log_action(current["username"], "hapus_gabungan_horeka", g)
                st.success(f"Grup '{g}' dihapus.")
                st.rerun()

st.divider()
st.subheader("Tambah grup baru")

with st.form("gabungan_form", clear_on_submit=True):
    group_name = st.text_input("Nama grup (jadi nama laporan gabungan)")
    wilayah = st.text_input("Wilayah (kode, mis. BTN/DKI/BLI/...)")
    site_codes = st.text_area("Kode site HOREKA yang digabung (satu per baris, minimal 2)", height=120)
    submitted = st.form_submit_button("Buat Grup", type="primary")

if submitted:
    name = group_name.strip()
    wil = wilayah.strip().upper()
    codes = [c.strip() for c in site_codes.splitlines() if c.strip()]
    if not name or not wil:
        st.error("Nama grup dan wilayah wajib diisi.")
    elif len(codes) < 2:
        st.error("Minimal 2 kode site untuk digabung.")
    elif name in groups:
        st.error(f"Grup '{name}' sudah ada -- hapus dulu kalau mau ganti isinya.")
    else:
        outlet_names = _horeka_outlet_names()
        unknown = [c for c in codes if c not in outlet_names]
        if unknown:
            st.warning(
                "Kode berikut tidak ditemukan di data HOREKA saat ini (tetap disimpan, "
                "tapi periksa lagi -- mungkin salah ketik atau memang belum ada datanya): "
                + ", ".join(f"`{c}`" for c in unknown)
            )
        new_rows = pd.DataFrame([
            {"Wilayah": wil, "Site": c, "Outlet": outlet_names.get(c, ""), "Group": name}
            for c in codes
        ])
        combined = pd.concat([rows_df, new_rows], ignore_index=True)
        _save_rows(combined)
        db.log_action(current["username"], "buat_gabungan_horeka", f"{name} ({wil}): {', '.join(codes)}")
        st.success(f"Grup '{name}' dibuat dengan {len(codes)} toko.")
        st.rerun()
