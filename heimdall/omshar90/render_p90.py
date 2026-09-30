"""
render_p90.py
Format tampilan untuk rekap OMSHAR90 (Key Account / Outlet individual) --
pivot dari kolom lebar "Omset_<label>_QTY" (lihat omshar90_pipeline.py)
jadi tabel BRAND x bulan siap tampil, dengan subtotal Triwulan (TW,
rata-rata 3 bulan) diselipkan tiap akhir kuartal + RT2 (rata-rata tahunan)
+ rasio RT2 tahun ini vs tahun lalu -- meniru format yang SUDAH dipakai di
file referensi manual "D:\\Data BIA\\2026\\OMSET OUTLET\\OMS OUTLET P90
2026.xlsx" (dibongkar dulu sebelum modul ini ditulis, bukan tebakan).
"""

import pandas as pd

MONTHS_ID = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGS", "SEP", "OKT", "NOV", "DES"]
QUARTERS = [("TW1", MONTHS_ID[0:3]), ("TW2", MONTHS_ID[3:6]), ("TW3", MONTHS_ID[6:9]), ("TW4", MONTHS_ID[9:12])]


def _fmt_num(v) -> str:
    """Gaya accounting: 2 desimal, koma sbg desimal (format Indonesia),
    '-' untuk nol/kosong -- konsisten dengan format yang sudah dipakai di
    Outlet Lapisan MClub untuk angka KRT."""
    if pd.isna(v) or v == 0:
        return "-"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"({s})" if v < 0 else s


def _fmt_ratio(v) -> str:
    if pd.isna(v) or v in (0, float("inf")):
        return "-"
    return f"{v * 100:.0f}%"


def _year_block(df: pd.DataFrame, year: int, metric: str) -> tuple[pd.DataFrame, list[str]]:
    """Kolom bulan (+ TW tiap akhir kuartal) + RT2 untuk SATU tahun --
    kolom sumbernya "Omset_<BULAN> <tahun>_<metric>" (harus sudah ada di df,
    dari omshar90_pipeline.read_sheet()). Return (dataframe kolom baru,
    urutan nama kolom) -- urutan dikembalikan terpisah karena nama kolom TW
    tahun 25/26 bisa sama-sama "TW1" kalau tidak disuffix tahun."""
    yy = str(year)[2:]
    out = pd.DataFrame(index=df.index)
    col_order = []
    for tw_label, months in QUARTERS:
        month_labels_this_q = []
        for m in months:
            src = f"Omset_{m} {year}_{metric}"
            label = f"{m} {yy}"
            out[label] = df[src] if src in df.columns else 0.0
            col_order.append(label)
            month_labels_this_q.append(label)
        tw_col = f"{tw_label} {yy}"
        out[tw_col] = out[month_labels_this_q].mean(axis=1)
        col_order.append(tw_col)

    rt2_col = f"RT2 {yy}"
    src_rt2 = f"Omset_RT2 {year}_{metric}"
    if src_rt2 in df.columns:
        out[rt2_col] = df[src_rt2]
    else:
        out[rt2_col] = out[[f"{m} {yy}" for q in QUARTERS for m in q[1]]].mean(axis=1)
    col_order.append(rt2_col)
    return out, col_order


def build_display_table(
    rekap_df: pd.DataFrame,
    label_col: str,
    label_header: str,
    metric: str = "QTY",
    years: tuple[int, int] = (2025, 2026),
) -> pd.DataFrame:
    """Tabel siap tampil: [label_header] + tahun pertama (bulan+TW+RT2) +
    tahun kedua (bulan+TW+RT2) + "RT2 <yy2> VS RT2 <yy1>" (rasio). Angka
    SUDAH diformat jadi string (siap render) -- pemanggil tidak perlu
    format ulang. `rekap_df` harus dari compute_rekap_key_account() atau
    compute_rekap_outlet() (omshar90_pipeline.py), sudah difilter ke SATU
    key account/outlet sebelum dipanggil."""
    if rekap_df.empty:
        return rekap_df

    y1, y2 = years
    block1, cols1 = _year_block(rekap_df, y1, metric)
    block2, cols2 = _year_block(rekap_df, y2, metric)

    yy1, yy2 = str(y1)[2:], str(y2)[2:]
    ratio_col = f"RT2 {yy2} VS RT2 {yy1}"
    ratio_raw = block2[f"RT2 {yy2}"] / block1[f"RT2 {yy1}"].replace(0, pd.NA)

    display = pd.DataFrame({label_header: rekap_df[label_col].values})
    for c in cols1:
        display[c] = block1[c].apply(_fmt_num).values
    for c in cols2:
        display[c] = block2[c].apply(_fmt_num).values
    display[ratio_col] = ratio_raw.apply(_fmt_ratio).values

    return display


def is_tw_or_rt2_col(col: str) -> bool:
    """Dipakai pemanggil (mis. buat bold/warna beda) -- kolom subtotal
    (TW1-4, RT2) vs kolom bulan biasa."""
    return col.startswith("TW") or col.startswith("RT2")


# Skema warna PERSIS sama dengan render_outlet_image.py (Omset Seeker) --
# 2025 peach + RT2 25 merah | BRAND biru muda | 2026 putih + RT2 26 biru tua
# -- supaya tabel P90 ini kelihatan satu keluarga tampilan dengan Omset
# Seeker, bukan tabel Streamlit polos. TW diberi warna lebih gelap dari
# bulan biasa di tahun yang sama (subtotal, bukan sekadar bulan), tapi
# lebih terang dari RT2 (subtotal kuartal < subtotal tahunan).
C_HEADER_25 = "#FCE0C3"
C_HEADER_TW_25 = "#F5C695"
C_HEADER_RT2_25 = "#E8281A"
C_HEADER_LABEL = "#F8E2A8"
C_HEADER_26 = "#FFFFFF"
C_HEADER_TW_26 = "#DCEAF6"
C_HEADER_RT2_26 = "#1F6FB2"
C_HEADER_RATIO = "#3D5A80"
C_CELL_TW_25 = "#FDEEDD"
C_CELL_RT2_25 = "#FBE3E1"
C_CELL_LABEL = "#EAF1FB"
C_CELL_TW_26 = "#EEF5FB"
C_CELL_RT2_26 = "#DCEAF6"
C_CELL_RATIO = "#E8EEF5"

_LABEL_COL_WIDTH = "min-width:180px;width:180px;"
_STICKY = "position:sticky;left:0;z-index:2;box-shadow:2px 0 3px -1px rgba(0,0,0,0.3);"


def _classify_col(col: str, label_header: str) -> str:
    if col == label_header:
        return "label"
    if " VS " in col:
        return "ratio"
    if col.startswith("TW"):
        return "tw_25" if col.endswith(" 25") else "tw_26"
    if col.startswith("RT2"):
        return "rt2_25" if col.endswith(" 25") else "rt2_26"
    return "month_25" if col.endswith(" 25") else "month_26"


_HEADER_BG = {
    "label": C_HEADER_LABEL, "month_25": C_HEADER_25, "tw_25": C_HEADER_TW_25,
    "rt2_25": C_HEADER_RT2_25, "month_26": C_HEADER_26, "tw_26": C_HEADER_TW_26,
    "rt2_26": C_HEADER_RT2_26, "ratio": C_HEADER_RATIO,
}
_CELL_BG = {
    "label": C_CELL_LABEL, "month_25": "white", "tw_25": C_CELL_TW_25,
    "rt2_25": C_CELL_RT2_25, "month_26": "white", "tw_26": C_CELL_TW_26,
    "rt2_26": C_CELL_RT2_26, "ratio": C_CELL_RATIO,
}
_WHITE_TEXT_KINDS = {"rt2_25", "rt2_26", "ratio"}


def build_html_table(display_df: pd.DataFrame, label_header: str) -> str:
    """Render `display_df` (hasil build_display_table()) jadi tabel HTML
    dengan skema warna sama seperti Omset Seeker -- lihat komentar warna
    di atas. Kolom label (BRAND) di-freeze (position:sticky) ke kiri,
    sama seperti render_outlet_image.build_html_table()."""
    if display_df.empty:
        return "<p>(kosong)</p>"

    cols = list(display_df.columns)
    kinds = {c: _classify_col(c, label_header) for c in cols}

    def th(col):
        kind = kinds[col]
        bg = _HEADER_BG[kind]
        fg = "white" if kind in _WHITE_TEXT_KINDS else "black"
        extra = _STICKY + _LABEL_COL_WIDTH if kind == "label" else ""
        return (
            f'<th style="background:{bg};color:{fg};padding:4px 8px;white-space:nowrap;'
            f'border:1px solid #999;{extra}">{col}</th>'
        )

    def td(col, val):
        kind = kinds[col]
        bg = _CELL_BG[kind]
        fg = "white" if kind in _WHITE_TEXT_KINDS else "black"
        bold = kind != "month_25" and kind != "month_26"
        align = "left" if kind == "label" else "right"
        extra = _STICKY + _LABEL_COL_WIDTH if kind == "label" else ""
        return (
            f'<td style="background:{bg};color:{fg};padding:4px 8px;text-align:{align};'
            f'border:1px solid #ccc;{"font-weight:bold;" if bold else ""}white-space:nowrap;{extra}">{val}</td>'
        )

    header = "<tr>" + "".join(th(c) for c in cols) + "</tr>"
    body_rows = []
    for _, row in display_df.iterrows():
        body_rows.append("<tr>" + "".join(td(c, row[c]) for c in cols) + "</tr>")

    return f"""
    <div style="overflow-x:auto; border:1px solid #999; border-radius:4px;">
      <table style="border-collapse:collapse; font-size:0.8rem; width:100%;">
        <thead>{header}</thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
    """
