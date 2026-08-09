"""
CEK CUTOFF OMSHAR
Baca tanggal cutoff LANGSUNG dari tiap file .xls mentah di D:\\DB OMSHAR\\DB
(bukan dari hasil transpose) -- supaya bisa lihat brand mana yang sudah/belum
ke-sync data terbarunya SEBELUM jalankan Transpose, bukan baru ketahuan sesudahnya.
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import auth

sys.path.insert(0, str(Path(r"D:\SDAAREA\omset_pipeline")))
import transpose as t  # noqa: E402

auth.require_level(5, page="Cek Cutoff OMSHAR")
st.title("Cek Cutoff OMSHAR")
st.caption(
    "Cutoff diambil dari baris 'PERIODE : ...' di dalam tiap file OMSHAR mentah itu "
    "sendiri -- bukan dari hasil Transpose, jadi bisa dicek SEBELUM Transpose "
    "dijalankan, untuk tahu brand mana yang perlu di-Sync ulang."
)

OMSHAR_DIR = Path(r"D:\DB OMSHAR\DB")


def _read_file_cutoff(path: Path):
    if not path.exists():
        return None
    import xlrd
    try:
        wb = xlrd.open_workbook(str(path), on_demand=True)
        names = wb.sheet_names()
        if not names:
            return None
        sh = wb.sheet_by_name(names[0])
        periode_text = str(sh.cell_value(2, 0))
        wb.release_resources()
        date_part = periode_text.split("sd")[-1].strip()
        day, month, year = date_part.split("/")
        return datetime(int(year), int(month), int(day))
    except Exception:
        return None


def _collect_rows(category: str, file_map: dict, label_suffix: str = "") -> list:
    rows = []
    for brand, files in file_map.items():
        for file_name in files:
            path = OMSHAR_DIR / f"OMSHAR {category} {file_name}.xls"
            exists = path.exists()
            cutoff = _read_file_cutoff(path) if exists else None
            mtime = datetime.fromtimestamp(path.stat().st_mtime) if exists else None
            rows.append({
                "Brand": f"{brand}{label_suffix}",
                "File": file_name,
                "Ada": exists,
                "Cutoff (isi file)": cutoff,
                "Terakhir disync": mtime,
            })
    return rows


@st.cache_data(show_spinner=False, ttl="10m")
def build_cutoff_table(category: str) -> pd.DataFrame:
    file_map = t.UMUM_FILE if category == "UMUM" else t.HOREKA_FILE
    rows = _collect_rows(category, file_map)
    if category == "HOREKA":
        rows += _collect_rows("HOREKA", t.HOREKA_KEG_FILE, label_suffix=" (KEG)")
    return pd.DataFrame(rows)


category = st.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="cutoff_cat")

col_cap, col_btn = st.columns([5, 1])
col_cap.caption(f"Sumber: `{OMSHAR_DIR}`")
if col_btn.button("Refresh"):
    build_cutoff_table.clear()
    st.rerun()

df = build_cutoff_table(category)

if df.empty:
    st.info("Tidak ada data.")
else:
    max_cutoff = df["Cutoff (isi file)"].max()

    def _status(row):
        if not row["Ada"] or pd.isna(row["Cutoff (isi file)"]):
            return "Tidak terbaca"
        if row["Cutoff (isi file)"] == max_cutoff:
            return "Terbaru"
        return "KETINGGALAN"

    df["Status"] = df.apply(_status, axis=1)

    n_total = len(df)
    n_latest = int((df["Status"] == "Terbaru").sum())
    n_stale = int((df["Status"] == "KETINGGALAN").sum())
    n_missing = int((df["Status"] == "Tidak terbaca").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cutoff terbaru ditemukan", max_cutoff.strftime("%d %b %Y") if pd.notna(max_cutoff) else "-")
    c2.metric("Sudah terbaru", f"{n_latest}/{n_total}")
    c3.metric("Ketinggalan", n_stale, delta=None, delta_color="inverse")
    c4.metric("Tidak terbaca/belum ada", n_missing)

    only_issues = st.checkbox("Tampilkan yang bermasalah saja (ketinggalan / tidak terbaca)", value=(n_stale + n_missing > 0))

    show = df.copy()
    if only_issues:
        show = show[show["Status"] != "Terbaru"]
    show = show.sort_values(["Status", "Brand"])

    # Kolom "Ada" (boolean) di-drop dari tampilan -- checkbox True/False dari
    # st.dataframe nyaris tidak kelihatan di atas warna highlight baris pada
    # tema gelap (dilaporkan user). Statusnya sendiri sudah cukup mewakili.
    # Tanggal diformat jadi teks biasa juga -- versi mentah pandas Timestamp
    # (dengan mikrodetik utk "Terakhir disync") berantakan dibaca di tabel.
    show = show.drop(columns=["Ada"])
    show["Cutoff (isi file)"] = show["Cutoff (isi file)"].apply(
        lambda d: d.strftime("%d %b %Y") if pd.notna(d) else "-"
    )
    show["Terakhir disync"] = show["Terakhir disync"].apply(
        lambda d: d.strftime("%d %b %Y %H:%M") if pd.notna(d) else "-"
    )

    def _highlight(row):
        if row["Status"] == "KETINGGALAN":
            return ["background-color: #f8d7da; color: #000;"] * len(row)
        if row["Status"] == "Tidak terbaca":
            return ["background-color: #fff3cd; color: #000;"] * len(row)
        return [""] * len(row)

    try:
        st.dataframe(
            show.style.apply(_highlight, axis=1),
            use_container_width=True, hide_index=True,
        )
    except Exception:
        # fallback kalau styling row-level tidak didukung versi Streamlit ini
        st.dataframe(show, use_container_width=True, hide_index=True)
