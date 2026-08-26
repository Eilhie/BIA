"""
RENDER BPR
Tampilan (HTML web + export Excel/PDF) untuk Rekap Per Depo / Per Wilayah --
format di-copy PERSIS dari "BPR BIA DAILY TEMPLATE.xlsx" (dicek langsung
lewat openpyxl cell.fill/font/number_format/merged_cells, bukan tebakan):
  - Warna: DATA (NORM/STOK/DOI) kuning FFFF00, PROPOSED ORDER hijau FF00FF00
    (PROST LAGER..WEISSBIER) / oranye FFC000 (SINGARAJA ARAK, BAESOMAEK,
    SINGARAJA PALE ALE), TOTAL merah FF0000, ACTUAL ORDER/% gelap teks putih.
  - Header 2 baris digabung (merged cell): baris atas nama grup (DATA,
    PROPOSED ORDER), baris bawah nama kolom (NORM/STOK/DOI, brand, TOTAL) --
    WILAYAH/DEPO/ACTUAL ORDER/% span vertikal 2 baris tanpa sub-header.
  - Font Calibri BOLD di SEMUA sel (bukan cuma header) -- pilihan gaya
    template asli, dicek langsung (cell.font.bold=True bahkan di baris data).
  - Format angka accounting 0 desimal (dash '-' untuk nol) di SEMUA kolom
    angka termasuk STOK & DOI (bukan 2/1 desimal kayak biasanya di app ini) --
    persis number_format template (`_(* #,##0_);...;_(* "-"??_);...`).
    Kolom % pakai '0%' (0 desimal, bukan 1).
  - Judul besar "BPR BIA" 28pt + subjudul 18pt (diisi tanggal file sumber
    yang SEBENARNYA, bukan label statis "UPDATE ..." yang di template asli
    ternyata sering lupa di-update manual).
"""

import io
import re

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

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

FONT_NAME = "Calibri, sans-serif"

_RAW_TS_RE = re.compile(r"BPR_BIA-(\d{14})\.xls")
_MONTH_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def format_update_label(source_name: str) -> str:
    """'BPR_BIA-20260824070100.xls' -> 'UPDATE 24 Agustus 2026 07:01' -- dinamis
    dari timestamp NYATA di nama file, gantiin label statis 'UPDATE 18 MEI 2026'
    di template yang sering lupa di-update manual (lihat bpr_pipeline.py)."""
    m = _RAW_TS_RE.search(source_name)
    if not m:
        return source_name
    ts = m.group(1)
    y, mo, d, hh, mm = int(ts[:4]), int(ts[4:6]), int(ts[6:8]), int(ts[8:10]), int(ts[10:12])
    return f"UPDATE {d} {_MONTH_ID[mo]} {y} {hh:02d}:{mm:02d}"


def _is_prev_total_col(col: str) -> bool:
    """'TOTAL 24 Ags 2026' (label dinamis dari previous_total_label()) -- beda
    dari kolom 'TOTAL' biasa, jadi dicek via prefix bukan exact match."""
    return col.startswith("TOTAL ") and col != "TOTAL"


def _col_fill(col: str) -> str:
    if col in ("NORM", "STOK", "DOI"):
        return C_DATA
    if col in BRAND_GROUP_1:
        return C_BRAND_1
    if col in BRAND_GROUP_2:
        return C_BRAND_2
    if col == "TOTAL" or _is_prev_total_col(col):
        return C_TOTAL
    if col in ("ACTUAL ORDER", "%"):
        return C_DARK
    return C_WHITE


def _col_font(col: str) -> str:
    return C_WHITE if col in ("ACTUAL ORDER", "%") else "000000"


def _fmt_num(v) -> str:
    """Gaya accounting template asli: 0 desimal, '-' untuk nol/kosong, kurung
    untuk negatif -- BUKAN 2/1 desimal yang biasa dipakai di halaman lain."""
    if pd.isna(v) or v == 0:
        return "-"
    s = f"{abs(v):,.0f}".replace(",", ".")
    return f"({s})" if v < 0 else s


def _fmt_pct(v) -> str:
    if pd.isna(v):
        return "-"
    return f"{v * 100:.0f}%"


def _fmt_cell(col: str, v):
    return _fmt_pct(v) if col == "%" else _fmt_num(v)


def _cols(df: pd.DataFrame) -> tuple[list, list]:
    id_cols = [c for c in ["Wilayah", "Depo"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols]
    return id_cols, value_cols


def _is_total_row(row) -> bool:
    return str(row.get("Depo", row.get("Wilayah", ""))).strip().upper().endswith("TOTAL")


def _header_groups(value_cols: list) -> list[tuple[str, list, str]]:
    """[(label_grup, [kolom...], warna_grup)] -- 'DATA' menaungi NORM/STOK/DOI,
    'PROPOSED ORDER' menaungi 10 brand + TOTAL, sama persis merge H3:R3 /
    D3:F3 di template (satu warna utuh per grup, warna sub-kolom cuma tampil
    di baris kedua -- itu juga perilaku asli Excel utk merged cell)."""
    groups = []
    data_cols = [c for c in ("NORM", "STOK", "DOI") if c in value_cols]
    if data_cols:
        groups.append(("DATA", data_cols, C_DATA))
    order_cols = [c for c in bp.BRAND_COLUMNS if c in value_cols] + (["TOTAL"] if "TOTAL" in value_cols else [])
    if order_cols:
        groups.append(("PROPOSED ORDER", order_cols, C_BRAND_1))
    handled = set(data_cols) | set(order_cols)
    # Kolom lain (ACTUAL ORDER, %, dan TOTAL <tanggal lalu> yang labelnya
    # dinamis dari previous_total_label()) -- masing-masing grup sendiri
    # (span 2 baris, tanpa sub-header), warna diambil dari _col_fill() supaya
    # otomatis benar apa pun nama kolomnya.
    for c in value_cols:
        if c not in handled:
            groups.append((c, [c], _col_fill(c)))
    return groups


def build_html_table(df: pd.DataFrame, title: str, update_label: str) -> str:
    """Tabel HTML header 2-baris + warna + format PERSIS template Excel."""
    id_cols, value_cols = _cols(df)
    groups = _header_groups(value_cols)

    def th(text, bg, fg="000000", colspan=1, rowspan=1):
        span = f' colspan="{colspan}"' if colspan > 1 else ""
        span += f' rowspan="{rowspan}"' if rowspan > 1 else ""
        return (
            f'<th{span} style="background:#{bg};color:#{fg};padding:4px 8px;white-space:nowrap;'
            f'border:1px solid #999;text-align:center;font-family:{FONT_NAME};">{text}</th>'
        )

    row1 = "<tr>"
    for c in id_cols:
        row1 += th(c.upper(), "FFFFFF", rowspan=2)
    for label, cols, color in groups:
        row1 += th(label, color, _col_font(cols[0]), colspan=len(cols))
    row1 += "</tr>"

    row2 = "<tr>"
    for label, cols, _ in groups:
        if len(cols) == 1 and cols[0] == label:
            continue  # ACTUAL ORDER / % -- sudah rowspan=2 di row1, tidak ada sel row2
        for c in cols:
            row2 += th(c, _col_fill(c), _col_font(c))
    row2 += "</tr>"

    body_rows = []
    for _, row in df.iterrows():
        is_total = _is_total_row(row)
        row_bg = "#EEEEEE" if is_total else "white"
        cells = ""
        for c in id_cols:
            v = row[c] if pd.notna(row[c]) else ""
            cells += (
                f'<td style="background:{row_bg};color:#000;padding:4px 8px;text-align:left;'
                f'border:1px solid #ccc;font-weight:bold;white-space:nowrap;font-family:{FONT_NAME};">{v}</td>'
            )
        for c in value_cols:
            cells += (
                f'<td style="background:{row_bg};color:#000;padding:4px 8px;text-align:right;'
                f'border:1px solid #ccc;font-weight:bold;white-space:nowrap;font-family:{FONT_NAME};">'
                f'{_fmt_cell(c, row[c])}</td>'
            )
        body_rows.append(f"<tr>{cells}</tr>")

    return f"""
    <div style="overflow-x:auto; border:1px solid #999; border-radius:4px; font-family:{FONT_NAME};">
      <div style="padding:8px 10px 0 10px; font-weight:bold; font-size:1.8rem;">BPR BIA</div>
      <div style="padding:0 10px 8px 10px; font-weight:bold; font-size:1.1rem;">{update_label}</div>
      <div style="padding:0 10px 6px 10px; font-size:0.85rem; color:#888;">{title}</div>
      <table style="border-collapse:collapse; font-size:0.8rem; width:100%;">
        <thead>{row1}{row2}</thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
    """


def build_excel_bytes(depo_df: pd.DataFrame, wilayah_df: pd.DataFrame, update_label: str) -> bytes:
    """Excel dengan warna/format/header gabung PERSIS template asli -- 2 sheet,
    sama seperti 'Rekap Per DEPO' + 'Rekap Per WILAYAH' di file sumbernya."""
    wb = openpyxl.Workbook()
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    BOLD = Font(name="Calibri", bold=True, size=11)

    def write_sheet(ws, df: pd.DataFrame, sheet_title: str):
        ws.title = sheet_title
        ws.sheet_view.showGridLines = False
        id_cols, value_cols = _cols(df)
        groups = _header_groups(value_cols)

        ws.cell(row=1, column=1, value="BPR BIA").font = Font(name="Calibri", bold=True, size=28)
        ws.cell(row=2, column=1, value=update_label).font = Font(name="Calibri", bold=True, size=18)
        ws.row_dimensions[1].height = 36
        ws.row_dimensions[2].height = 23.5
        ws.row_dimensions[4].height = 43.5

        row1, row2 = 3, 4
        col_i = 1
        for c in id_cols:
            ws.merge_cells(start_row=row1, start_column=col_i, end_row=row2, end_column=col_i)
            cell = ws.cell(row=row1, column=col_i, value=c.upper())
            cell.font = BOLD
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for r in (row1, row2):
                ws.cell(row=r, column=col_i).border = border
            col_i += 1

        col_positions: dict[str, int] = {}
        for label, cols, color in groups:
            is_tall = len(cols) == 1 and cols[0] == label
            start_col = col_i
            for c in cols:
                col_positions[c] = col_i
                col_i += 1
            end_col = col_i - 1
            if is_tall:
                ws.merge_cells(start_row=row1, start_column=start_col, end_row=row2, end_column=end_col)
            else:
                ws.merge_cells(start_row=row1, start_column=start_col, end_row=row1, end_column=end_col)
            top_cell = ws.cell(row=row1, column=start_col, value=label)
            top_cell.font = Font(name="Calibri", bold=True, color=_col_font(cols[0]))
            top_cell.fill = PatternFill("solid", fgColor=color)
            top_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for cc in range(start_col, end_col + 1):
                ws.cell(row=row1, column=cc).border = border
                ws.cell(row=row2, column=cc).border = border
            if not is_tall:
                for c in cols:
                    cell = ws.cell(row=row2, column=col_positions[c], value=c)
                    cell.font = Font(name="Calibri", bold=True, color=_col_font(c))
                    cell.fill = PatternFill("solid", fgColor=_col_fill(c))
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for r_off, (_, row) in enumerate(df.iterrows(), start=row2 + 1):
            is_total = _is_total_row(row)
            for i, c in enumerate(id_cols, start=1):
                cell = ws.cell(row=r_off, column=i, value=None if pd.isna(row[c]) else row[c])
                cell.font = BOLD
                cell.border = border
                if is_total:
                    cell.fill = PatternFill("solid", fgColor="EEEEEE")
            for c, j in col_positions.items():
                v = row[c]
                cell = ws.cell(row=r_off, column=j, value=None if pd.isna(v) else float(v))
                cell.font = BOLD
                cell.border = border
                cell.number_format = "0%" if c == "%" else '_(* #,##0_);_(* (#,##0);_(* "-"??_);_(@_)'
                if is_total:
                    cell.fill = PatternFill("solid", fgColor="EEEEEE")

        ws.column_dimensions[get_column_letter(1)].width = 25.4 if "Wilayah" in id_cols else 25.4
        if "Depo" in id_cols:
            ws.column_dimensions[get_column_letter(2)].width = 22.9
        for c, j in col_positions.items():
            ws.column_dimensions[get_column_letter(j)].width = 18 if c in bp.BRAND_COLUMNS else 11

    write_sheet(wb.active, depo_df, "Rekap Per DEPO")
    write_sheet(wb.create_sheet(), wilayah_df, "Rekap Per WILAYAH")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _build_table_figure(df: pd.DataFrame, title: str, update_label: str) -> "Figure":
    id_cols, value_cols = _cols(df)
    groups = _header_groups(value_cols)
    cols = id_cols + value_cols
    n_rows = len(df) + 2  # +2 header baris (grup + sub)
    n_cols = len(cols)

    fig_w = sum(3.0 if c in id_cols else 1.15 for c in cols)
    fig_h = 0.28 * n_rows + 1.2
    fig = Figure(figsize=(fig_w, fig_h), dpi=150)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.88])
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, n_rows)
    ax.invert_yaxis()
    ax.axis("off")
    fig.text(0.01, 0.985, "BPR BIA", fontsize=16, fontweight="bold")
    fig.text(0.01, 0.955, update_label, fontsize=10, fontweight="bold")
    fig.text(0.01, 0.93, title, fontsize=7, color="#666")

    col_x = [0.0]
    for c in cols:
        col_x.append(col_x[-1] + (3.0 if c in id_cols else 1.15))

    rects, colors = [], []
    # baris 0: grup header, baris 1: sub header (id_cols & tall groups span kedua baris)
    ci = 0
    for c in id_cols:
        rects.append(Rectangle((col_x[ci], 0), col_x[ci + 1] - col_x[ci], 2))
        colors.append((1, 1, 1))
        ci += 1
    for label, gcols, color in groups:
        is_tall = len(gcols) == 1 and gcols[0] == label
        span = len(gcols)
        rgb = _hex_rgb(color)
        if is_tall:
            rects.append(Rectangle((col_x[ci], 0), col_x[ci + span] - col_x[ci], 2))
            colors.append(rgb)
        else:
            rects.append(Rectangle((col_x[ci], 0), col_x[ci + span] - col_x[ci], 1))
            colors.append(rgb)
            for k, c in enumerate(gcols):
                rects.append(Rectangle((col_x[ci + k], 1), col_x[ci + k + 1] - col_x[ci + k], 1))
                colors.append(_hex_rgb(_col_fill(c)))
        ci += span

    for ri, (_, row) in enumerate(df.iterrows(), start=2):
        bg = (0.93, 0.93, 0.93) if _is_total_row(row) else (1, 1, 1)
        for c in range(n_cols):
            rects.append(Rectangle((col_x[c], ri), col_x[c + 1] - col_x[c], 1))
            colors.append(bg)

    ax.add_collection(PatchCollection(rects, facecolor=colors, edgecolor="#999", linewidth=0.4))

    ci = 0
    for c in id_cols:
        ax.text((col_x[ci] + col_x[ci + 1]) / 2, 1, c.upper(), ha="center", va="center",
                 fontsize=6, fontweight="bold")
        ci += 1
    for label, gcols, color in groups:
        is_tall = len(gcols) == 1 and gcols[0] == label
        span = len(gcols)
        fg = "white" if label in ("ACTUAL ORDER", "%") else "black"
        y = 1 if is_tall else 0.5
        ax.text((col_x[ci] + col_x[ci + span]) / 2, y, label, ha="center", va="center",
                 fontsize=6, fontweight="bold", color=fg)
        if not is_tall:
            for k, c in enumerate(gcols):
                fg2 = "white" if c in ("ACTUAL ORDER", "%") else "black"
                ax.text((col_x[ci + k] + col_x[ci + k + 1]) / 2, 1.5, c, ha="center", va="center",
                         fontsize=5, fontweight="bold", color=fg2)
        ci += span

    for ri, (_, row) in enumerate(df.iterrows(), start=2):
        for c_i, c in enumerate(cols):
            if c in id_cols:
                text = "" if pd.isna(row[c]) else str(row[c])
                align = "left"
                x = col_x[c_i] + 0.05
            else:
                text = _fmt_cell(c, row[c])
                align = "right"
                x = col_x[c_i + 1] - 0.05
            ax.text(x, ri + 0.5, text, ha=align, va="center", fontsize=5.5, fontweight="bold")

    return fig


def build_pdf_bytes(depo_df: pd.DataFrame, wilayah_df: pd.DataFrame, update_label: str) -> bytes:
    """PDF 2 halaman (Rekap Per Depo, Rekap Per Wilayah) -- render via matplotlib
    (pola sama seperti render_outlet_image.py: Figure + PatchCollection, savefig
    ke format 'pdf' alih-alih 'png')."""
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError(f"matplotlib tidak bisa dimuat: {_MATPLOTLIB_IMPORT_ERROR}")

    from matplotlib.backends.backend_pdf import PdfPages

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for df, title in [(depo_df, "Rekap Per Depo"), (wilayah_df, "Rekap Per Wilayah")]:
            fig = _build_table_figure(df, title, update_label)
            pdf.savefig(fig, bbox_inches="tight")
    return buf.getvalue()
