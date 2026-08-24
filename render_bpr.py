"""
RENDER BPR
Tampilan (HTML web + export Excel/PDF) untuk Rekap Per Depo / Per Wilayah --
warna & pengelompokan kolom di-copy PERSIS dari "BPR BIA DAILY TEMPLATE.xlsx"
(dicek langsung lewat openpyxl cell.fill, bukan tebakan):
  - DATA (NORM/STOK/DOI)              -> kuning FFFF00
  - PROPOSED ORDER brand grup 1       -> hijau  00FF00 (PROST LAGER..WEISSBIER)
  - PROPOSED ORDER brand grup 2       -> oranye FFC000 (SINGARAJA ARAK, BAESOMAEK, SINGARAJA PALE ALE)
  - TOTAL                             -> merah  FF0000
  - ACTUAL ORDER / %                  -> gelap  1F1F1F (teks putih)
"""

import io

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

try:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import PatchCollection
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    MATPLOTLIB_AVAILABLE = True
except Exception as e:  # pragma: no cover
    MATPLOTLIB_AVAILABLE = False
    _MATPLOTLIB_IMPORT_ERROR = e

import bpr_pipeline as bp

C_DATA = "FFFF00"
C_BRAND_1 = "00FF00"
C_BRAND_2 = "FFC000"
C_TOTAL = "FF0000"
C_DARK = "1F1F1F"
C_WHITE = "FFFFFF"

BRAND_GROUP_1 = bp.BRAND_COLUMNS[:7]
BRAND_GROUP_2 = bp.BRAND_COLUMNS[7:]


def _col_fill(col: str) -> str:
    if col in ("NORM", "STOK", "DOI"):
        return C_DATA
    if col in BRAND_GROUP_1:
        return C_BRAND_1
    if col in BRAND_GROUP_2:
        return C_BRAND_2
    if col == "TOTAL":
        return C_TOTAL
    if col in ("ACTUAL ORDER", "%"):
        return C_DARK
    return C_WHITE


def _col_font(col: str) -> str:
    return C_WHITE if col in ("ACTUAL ORDER", "%") else "000000"


def _fmt_num(v, decimals=0) -> str:
    if pd.isna(v):
        return "-"
    return f"{v:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v) -> str:
    if pd.isna(v):
        return "-"
    return f"{v * 100:.1f}".replace(".", ",") + "%"


def _fmt_cell(col: str, v):
    if col == "%":
        return _fmt_pct(v)
    if col == "STOK":
        return _fmt_num(v, 2)
    if col == "DOI":
        return _fmt_num(v, 1)
    return _fmt_num(v, 0)


def build_html_table(df: pd.DataFrame, title: str) -> str:
    """Tabel HTML warna PERSIS template Excel -- dipakai buat tampilan on-screen
    di halaman Streamlit (bukan cuma heatmap generik seperti Cukai Kompetitor,
    karena user minta persis meniru file Excel-nya)."""
    id_cols = [c for c in ["Wilayah", "Depo"] for c in [c] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]

    def th(text, bg, fg="000000"):
        return (
            f'<th style="background:#{bg};color:#{fg};padding:4px 8px;white-space:nowrap;'
            f'border:1px solid #999;text-align:center;">{text}</th>'
        )

    header = "<tr>"
    for c in id_cols:
        header += th(c, "FFFFFF")
    for c in value_cols:
        header += th(c, _col_fill(c), _col_font(c))
    header += "</tr>"

    body_rows = []
    for _, row in df.iterrows():
        is_total_row = str(row.get("Depo", row.get("Wilayah", ""))).strip().upper().endswith("TOTAL")
        row_bg = "#EEEEEE" if is_total_row else "white"
        cells = ""
        for c in id_cols:
            v = row[c] if pd.notna(row[c]) else ""
            cells += (
                f'<td style="background:{row_bg};color:#000;padding:4px 8px;text-align:left;'
                f'border:1px solid #ccc;font-weight:bold;white-space:nowrap;">{v}</td>'
            )
        for c in value_cols:
            cells += (
                f'<td style="background:{row_bg};color:#000;padding:4px 8px;text-align:right;'
                f'border:1px solid #ccc;white-space:nowrap;">{_fmt_cell(c, row[c])}</td>'
            )
        body_rows.append(f"<tr>{cells}</tr>")

    return f"""
    <div style="overflow-x:auto; border:1px solid #999; border-radius:4px;">
      <div style="padding:6px 10px; font-weight:bold; font-size:1.05rem;">{title}</div>
      <table style="border-collapse:collapse; font-size:0.8rem; width:100%;">
        <thead>{header}</thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
    """


def build_excel_bytes(depo_df: pd.DataFrame, wilayah_df: pd.DataFrame, source_label: str) -> bytes:
    """Excel dengan warna/format PERSIS template asli -- 2 sheet, sama seperti
    'Rekap Per DEPO' + 'Rekap Per WILAYAH' di file sumbernya."""
    wb = openpyxl.Workbook()
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def write_sheet(ws, df: pd.DataFrame, sheet_title: str):
        ws.title = sheet_title
        id_cols = [c for c in ["Wilayah", "Depo"] for c in [c] if c in df.columns]
        value_cols = [c for c in df.columns if c not in id_cols]

        ws.cell(row=1, column=1, value="BPR BIA").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=source_label).font = Font(bold=True, italic=True)

        header_row = 4
        for i, c in enumerate(id_cols + value_cols, start=1):
            cell = ws.cell(row=header_row, column=i, value=c)
            cell.font = Font(bold=True, color=_col_font(c) if c in value_cols else "000000")
            if c in value_cols:
                cell.fill = PatternFill("solid", fgColor=_col_fill(c))
            cell.border = border
            cell.alignment = Alignment(horizontal="center")

        for r_off, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
            is_total_row = str(row.get("Depo", row.get("Wilayah", ""))).strip().upper().endswith("TOTAL")
            for i, c in enumerate(id_cols, start=1):
                cell = ws.cell(row=r_off, column=i, value=row[c])
                cell.font = Font(bold=True)
                cell.border = border
                if is_total_row:
                    cell.fill = PatternFill("solid", fgColor="EEEEEE")
            for j, c in enumerate(value_cols, start=len(id_cols) + 1):
                v = row[c]
                cell = ws.cell(row=r_off, column=j, value=None if pd.isna(v) else float(v))
                cell.border = border
                if c == "%":
                    cell.number_format = "0.0%"
                elif c == "STOK":
                    cell.number_format = "#,##0.00"
                elif c == "DOI":
                    cell.number_format = "#,##0.0"
                else:
                    cell.number_format = "#,##0"
                if is_total_row:
                    cell.fill = PatternFill("solid", fgColor="EEEEEE")
                    cell.font = Font(bold=True)

        for i, c in enumerate(id_cols + value_cols, start=1):
            ws.column_dimensions[ws.cell(row=header_row, column=i).column_letter].width = max(10, len(c) + 2)

    write_sheet(wb.active, depo_df, "Rekap Per DEPO")
    write_sheet(wb.create_sheet(), wilayah_df, "Rekap Per WILAYAH")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _build_table_figure(df: pd.DataFrame, title: str, source_label: str) -> "Figure":
    id_cols = [c for c in ["Wilayah", "Depo"] for c in [c] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]
    cols = id_cols + value_cols
    n_rows = len(df) + 1  # +1 header
    n_cols = len(cols)

    col_w = 1.5 if len(id_cols) else 1.0
    fig_w = sum(3.0 if c in id_cols else 1.15 for c in cols)
    fig_h = 0.28 * n_rows + 1.0
    fig = Figure(figsize=(fig_w, fig_h), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.9])
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, n_rows)
    ax.invert_yaxis()
    ax.axis("off")
    fig.text(0.01, 0.97, "BPR BIA", fontsize=13, fontweight="bold")
    fig.text(0.01, 0.94, f"{title} -- {source_label}", fontsize=8, color="#444")

    col_x = [0.0]
    for c in cols:
        col_x.append(col_x[-1] + (3.0 if c in id_cols else 1.15))

    rects, colors = [], []
    header_bg = {c: (_hex_rgb(_col_fill(c)) if c in value_cols else (1, 1, 1)) for c in cols}
    for ci, c in enumerate(cols):
        rects.append(Rectangle((col_x[ci], 0), col_x[ci + 1] - col_x[ci], 1))
        colors.append(header_bg[c])
    for ri, (_, row) in enumerate(df.iterrows(), start=1):
        is_total_row = str(row.get("Depo", row.get("Wilayah", ""))).strip().upper().endswith("TOTAL")
        bg = (0.93, 0.93, 0.93) if is_total_row else (1, 1, 1)
        for ci in range(n_cols):
            rects.append(Rectangle((col_x[ci], ri), col_x[ci + 1] - col_x[ci], 1))
            colors.append(bg)

    ax.add_collection(PatchCollection(rects, facecolor=colors, edgecolor="#999", linewidth=0.4))

    for ci, c in enumerate(cols):
        fg = "white" if c in ("ACTUAL ORDER", "%") else "black"
        ax.text((col_x[ci] + col_x[ci + 1]) / 2, 0.5, c, ha="center", va="center",
                 fontsize=6, fontweight="bold", color=fg)

    for ri, (_, row) in enumerate(df.iterrows(), start=1):
        for ci, c in enumerate(cols):
            if c in id_cols:
                text = "" if pd.isna(row[c]) else str(row[c])
                align = "left"
                x = col_x[ci] + 0.05
            else:
                text = _fmt_cell(c, row[c])
                align = "right"
                x = col_x[ci + 1] - 0.05
            ax.text(x, ri + 0.5, text, ha=align, va="center", fontsize=5.5)

    return fig


def build_pdf_bytes(depo_df: pd.DataFrame, wilayah_df: pd.DataFrame, source_label: str) -> bytes:
    """PDF 2 halaman (Rekap Per Depo, Rekap Per Wilayah) -- render via matplotlib
    (pola sama seperti render_outlet_image.py: Figure + PatchCollection, savefig
    ke format 'pdf' alih-alih 'png')."""
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError(f"matplotlib tidak bisa dimuat: {_MATPLOTLIB_IMPORT_ERROR}")

    from matplotlib.backends.backend_pdf import PdfPages

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for df, title in [(depo_df, "Rekap Per Depo"), (wilayah_df, "Rekap Per Wilayah")]:
            fig = _build_table_figure(df, title, source_label)
            pdf.savefig(fig, bbox_inches="tight")
    return buf.getvalue()
