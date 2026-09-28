"""
tools.py (Mimir)
Read-only tools that let Mimir's LLM call Heimdall's real query functions
instead of ever generating a number itself -- every figure Mimir reports
about an outlet must come out of one of these calls, never from the model.

SCOPE: outlet lookup only (Heimdall's level-1 "Omset Seeker" equivalent),
deliberately. Heimdall gates SKU-claim / dashboard data behind Admin login;
Mimir has no login, so exposing those here would silently bypass that gate.
Widening this list means deciding the access-control question first.

Each tool returns at least {"model_text": str, "table": DataFrame | None,
"title": str}. cari_outlet additionally returns "html" (Heimdall's own
report table markup) and "png_bytes"/"png_name" (Heimdall's own report
image, for the copy/print/download widget) -- both None if rendering
failed, since that's a display enhancement, not required for the tool
call itself. model_text is what the LLM sees; everything else is rendered
directly in the UI so the user sees the raw returned figures/report next
to the model's narration and can check one against the other.
"""

import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

HEIMDALL_DIR = Path(__file__).resolve().parent.parent / "heimdall"
VALID_TYPES = ("UMUM", "HOREKA")
MAX_SEARCH_RESULTS = 10


def _omset_seeker():
    """Imported lazily: keeps Mimir's startup fast and means a broken
    Heimdall import only fails a tool call, not the whole app."""
    if str(HEIMDALL_DIR) not in sys.path:
        sys.path.insert(0, str(HEIMDALL_DIR))
    from core import omset_seeker
    return omset_seeker


def _render_outlet_image():
    if str(HEIMDALL_DIR) not in sys.path:
        sys.path.insert(0, str(HEIMDALL_DIR))
    from core import render_outlet_image
    return render_outlet_image


def _render_outlet_visuals(site: str, tipe: str) -> dict:
    """Same rendering Heimdall's own Omset Seeker page uses (build_report_rows
    + build_html_table + render_outlet_report, core/render_outlet_image.py) --
    reused as-is (not reimplemented) so Mimir shows the real report layout and
    a real downloadable/printable PNG, not an LLM's prose narration of the
    numbers. build_report_rows() is computed ONCE and reused for both outputs
    (same `precomputed` pattern omset_search_app.py itself uses, so a lookup
    here doesn't query OMSHAR data three times over).

    Returns {} on any failure -- site genuinely not found is already handled
    by the caller via seek_outlet; this is purely a display enhancement, so a
    render failure (e.g. matplotlib blocked by Smart App Control, see
    render_outlet_report's own error message) must not break the tool call."""
    try:
        roi = _render_outlet_image()
        seeker = _omset_seeker()
        row_cells, info, cutoff = roi.build_report_rows(site, tipe)
        brand_cutoffs = {
            row[2]: seeker.get_cutoff_date(brand=row[2], omshar_type=tipe)
            for row in row_cells
        }
        html = roi.build_html_table(row_cells, cutoffs=brand_cutoffs)

        png_bytes = None
        try:
            _, png_bytes = roi.render_outlet_report(precomputed=(row_cells, info, cutoff))
        except Exception:
            pass  # PNG is a bonus on top of the HTML table, not required for it

        return {"html": html, "png_bytes": png_bytes, "info": info}
    except Exception:
        return {}


@lru_cache(maxsize=2)
def _outlet_index(tipe: str) -> pd.DataFrame:
    return _omset_seeker().build_outlet_index(tipe)


def _norm_type(tipe: str) -> str:
    tipe = (tipe or "UMUM").strip().upper()
    if tipe not in VALID_TYPES:
        raise ValueError(f"tipe harus salah satu dari {VALID_TYPES}, bukan '{tipe}'")
    return tipe


def cari_outlet(site: str, tipe: str = "UMUM", bulan_terakhir: int = 6) -> dict:
    tipe = _norm_type(tipe)
    site = (site or "").strip()
    if not site:
        raise ValueError("site number kosong")

    table, info = _omset_seeker().seek_outlet(site, tipe)
    if info is None:
        return {
            "model_text": f"Site '{site}' tidak ditemukan di data {tipe}.",
            "table": None,
            "title": f"cari_outlet({site}, {tipe}) -- tidak ditemukan",
        }

    # Only months that actually have any data, last N of those, and only
    # brands with something in that window -- the raw table is 20 brands x
    # 24 months, mostly zeros, which would bury the answer.
    has_data = [c for c in table.columns if table[c].fillna(0).ne(0).any()]
    cols = has_data[-max(1, int(bulan_terakhir)):]
    view = table[cols]
    view = view[view.fillna(0).ne(0).any(axis=1)].round(2)

    header = ", ".join(f"{k}: {v}" for k, v in info.items() if v not in (None, ""))

    # Spelled out cell by cell ("BRAND: BULAN=nilai; ...") instead of a wide
    # pandas grid, and with the latest month PRE-COMPUTED here. A 7-8B model
    # reading a grid misaligned cells (reported real numbers from other
    # months/brands against the wrong brand) and misjudged which month was
    # latest -- so the questions people obviously ask are answered by code,
    # not by the model's reading of a table.
    last_month = cols[-1]
    latest = "; ".join(f"{brand}={view.loc[brand, last_month]}" for brand in view.index)
    detail = "\n".join(
        f"- {brand}: " + "; ".join(f"{m}={view.loc[brand, m]}" for m in cols)
        for brand in view.index
    )
    visuals = _render_outlet_visuals(site, tipe)
    html = visuals.get("html")
    png_bytes = visuals.get("png_bytes")
    shown_note = (
        "Tabel laporan lengkap SUDAH ditampilkan ke user di bawah jawaban Anda -- "
        "jangan mengetik ulang seluruh rincian per bulan, cukup ringkas 1-2 kalimat "
        "(mis. bulan terakhir + hal yang ditanya) dan arahkan user melihat tabelnya."
        if html else ""
    )
    model_text = (
        f"Outlet -- {header}\n"
        f"Bulan yang ada datanya (lama ke baru): {', '.join(cols)}\n"
        f"BULAN TERAKHIR yang ada datanya: {last_month}\n"
        f"Nilai per brand di bulan terakhir ({last_month}), KRT: {latest}\n"
        f"Rincian per brand per bulan (KRT):\n{detail}\n"
        f"{shown_note}"
    )
    return {
        "model_text": model_text,
        "table": view,
        "html": html,
        "png_bytes": png_bytes,
        "png_name": f"{info.get('Site', site)} {info.get('Outlet', '')}.png",
        "title": f"cari_outlet(site={site}, tipe={tipe}) -- {info.get('Outlet', '')}",
    }


def cari_nama_outlet(kata_kunci: str, tipe: str = "UMUM") -> dict:
    tipe = _norm_type(tipe)
    kata_kunci = (kata_kunci or "").strip()
    if len(kata_kunci) < 3:
        raise ValueError("kata kunci minimal 3 huruf")

    idx = _outlet_index(tipe)
    hits = idx[idx["Outlet"].str.contains(kata_kunci, case=False, na=False, regex=False)]
    total = len(hits)
    if total == 0:
        return {
            "model_text": f"Tidak ada outlet {tipe} dengan nama mengandung '{kata_kunci}'.",
            "table": None,
            "title": f"cari_nama_outlet('{kata_kunci}', {tipe}) -- 0 hasil",
        }
    shown = hits.head(MAX_SEARCH_RESULTS).reset_index(drop=True)
    note = f" (menampilkan {len(shown)} pertama)" if total > len(shown) else ""
    return {
        "model_text": f"{total} outlet {tipe} cocok dengan '{kata_kunci}'{note}:\n{shown.to_string(index=False)}",
        "table": shown,
        "title": f"cari_nama_outlet('{kata_kunci}', {tipe}) -- {total} hasil",
    }


TOOL_FUNCS = {"cari_outlet": cari_outlet, "cari_nama_outlet": cari_nama_outlet}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "cari_outlet",
            "description": (
                "Ambil data omset (KRT per brand per bulan) untuk SATU outlet berdasarkan "
                "site number persis (format seperti 0815-02000166). Pakai HANYA kalau user "
                "meminta data/omset/angka outlet dan sudah menyebut site number-nya. Juga "
                "berlaku untuk outlet GABUNGAN (site code dari cari_nama_outlet yang bertanda "
                "'(Gabungan)') -- otomatis menjumlahkan semua toko anggotanya, tidak perlu "
                "tool terpisah."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {"type": "string", "description": "Site number outlet, mis. 0815-02000166"},
                    "tipe": {"type": "string", "enum": list(VALID_TYPES), "description": "Grup data, default UMUM"},
                    "bulan_terakhir": {"type": "integer", "description": "Berapa bulan terakhir yang ditampilkan, default 6"},
                },
                "required": ["site"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cari_nama_outlet",
            "description": (
                "Cari outlet berdasarkan potongan NAMA (bukan site number) untuk menemukan "
                "site number-nya. Pakai kalau user menyebut nama outlet tapi belum ada site "
                "number -- TERMASUK kalau user minta outlet/grup GABUNGAN (merged). Hasil "
                "gabungan ditandai '(Gabungan)' di kolom Outlet; tidak ditemukan berarti "
                "memang belum ada grup gabungan dengan nama itu, bukan berarti tool ini tidak "
                "mendukungnya."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kata_kunci": {"type": "string", "description": "Potongan nama outlet, minimal 3 huruf"},
                    "tipe": {"type": "string", "enum": list(VALID_TYPES), "description": "Grup data, default UMUM"},
                },
                "required": ["kata_kunci"],
            },
        },
    },
]


def run_tool(name: str, args: dict) -> dict:
    """Never raises -- a failed/unknown call becomes an error result the
    model can relay honestly, instead of crashing the chat turn."""
    func = TOOL_FUNCS.get(name)
    if func is None:
        return {"model_text": f"Tool '{name}' tidak dikenal.", "table": None, "title": f"{name} -- tidak dikenal"}
    try:
        return func(**(args or {}))
    except Exception as e:
        return {
            "model_text": f"Tool {name} gagal: {type(e).__name__}: {e}",
            "table": None,
            "title": f"{name} -- gagal",
        }
