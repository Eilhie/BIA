"""
OMSET SEARCH APP
Web app lokal (Streamlit, localhost saja -- tidak ter-expose ke jaringan)
untuk cari outlet dan lihat laporan OMSET OUTLET tanpa command line.

Jalankan lewat CARI OUTLET.bat, atau manual:
    streamlit run omset_search_app.py
"""

import base64

import streamlit as st
import streamlit.components.v1 as components

import pandas as pd

from omset_seeker import build_outlet_index, get_cutoff_date, load_brand, load_gabungan_map
from render_outlet_image import (
    C_CELL_BRAND,
    C_CELL_RT2_25,
    C_CELL_RT2_26,
    C_HEADER_25,
    C_HEADER_26,
    C_HEADER_BRAND,
    C_HEADER_RT2_25,
    C_HEADER_RT2_26,
    LABELS_25,
    LABELS_26,
    ROW_BG,
    build_report_excel,
    build_report_rows,
    render_outlet_report,
)

st.set_page_config(page_title="OMSET Seeker", layout="wide")
st.title("OMSET Seeker")

MAX_LIST_RESULTS = 30


def build_html_table(row_cells: list, cutoffs: dict[str, str] | None = None) -> str:
    """Tabel HTML yang meniru layout & warna OMSET OUTLET Excel/PNG asli:
    2025 (peach) + RT2 25 (merah) | BRAND (biru muda) | CUT OFF (opsional) |
    2026 (putih) + RT2 26 (biru tua).

    Kolom CUT OFF cuma tampil di tabel web ini (lewat parameter `cutoffs`),
    SENGAJA tidak disentuh di render_outlet_image.py sama sekali -- PNG yang
    dipakai Print/Copy/Excel jadi otomatis TIDAK ikut nampilkan kolom ini tanpa
    perlu CSS/logic khusus "sembunyikan saat print", karena keduanya memang
    jalur render yang benar-benar terpisah."""
    show_cutoff = cutoffs is not None
    th = lambda text, bg, fg="black": (
        f'<th style="background:{bg};color:{fg};padding:4px 8px;white-space:nowrap;'
        f'border:1px solid #999;">{text}</th>'
    )
    header = "<tr>"
    header += "".join(th(c, C_HEADER_25) for c in LABELS_25)
    header += th("RT2 25", C_HEADER_RT2_25, "white")
    header += th("BRAND", C_HEADER_BRAND)
    if show_cutoff:
        header += th("CUT OFF", C_HEADER_BRAND)
    header += "".join(th(c, C_HEADER_26) for c in LABELS_26)
    header += th("RT2 26", C_HEADER_RT2_26, "white")
    header += "</tr>"

    body_rows = []
    for vals_25, rt2_25, label, vals_26, rt2_26, row_type in row_cells:
        bg = ROW_BG[row_type]
        fg = "white" if row_type == "divab1" else "black"
        td = lambda text, cell_bg, align="right", bold=False: (
            f'<td style="background:{cell_bg};color:{fg};padding:4px 8px;text-align:{align};'
            f'border:1px solid #ccc;{"font-weight:bold;" if bold else ""}white-space:nowrap;">{text}</td>'
        )
        row = "<tr>"
        row += "".join(td(v, bg) for v in vals_25)
        row += td(rt2_25, bg if row_type != "normal" else C_CELL_RT2_25, bold=True)
        row += td(label, bg if row_type != "normal" else C_CELL_BRAND, align="left", bold=True)
        if show_cutoff:
            row += td(cutoffs.get(label, "") or "-", bg, align="center")
        row += "".join(td(v, bg) for v in vals_26)
        row += td(rt2_26, bg if row_type != "normal" else C_CELL_RT2_26, bold=True)
        row += "</tr>"
        body_rows.append(row)

    return f"""
    <div style="overflow-x:auto; border:1px solid #999; border-radius:4px;">
      <table style="border-collapse:collapse; font-size:0.8rem; width:100%;">
        <thead>{header}</thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
    """


@st.cache_data(show_spinner=False, ttl="10m")
def get_outlet_index(omshar_type: str):
    """Wrapper cache Streamlit di atas omset_seeker.build_outlet_index() -- dipakai sidebar
    buat browse/search outlet. Di-cache karena UMUM sendiri ~72rb baris, HOREKA ~15rb --
    tidak mau di-dedup ulang tiap keystroke."""
    return build_outlet_index(omshar_type)


def pick_outlet(site: str, omshar_type: str, with_keg: bool = False) -> None:
    st.session_state["last_query"] = (site, omshar_type, with_keg)


with st.sidebar:
    st.header("Daftar Outlet")
    list_type = st.radio("Grup", ["UMUM", "HOREKA"], horizontal=True, key="list_type")
    list_query = st.text_input("Cari nama/kode outlet", key="list_query", placeholder="ketik untuk mencari...")

    if list_query.strip():
        with st.spinner(f"Memuat daftar outlet {list_type}..."):
            outlets = get_outlet_index(list_type)
        q = list_query.strip().lower()
        matches = outlets[
            outlets["Outlet"].str.lower().str.contains(q, na=False, regex=False)
            | outlets["Site"].str.lower().str.contains(q, na=False, regex=False)
        ]
        n = len(matches)
        if n == 0:
            st.caption("Tidak ada outlet yang cocok.")
        else:
            shown = matches.head(MAX_LIST_RESULTS)
            st.caption(f"{n} hasil" + (f" (menampilkan {MAX_LIST_RESULTS} teratas)" if n > MAX_LIST_RESULTS else ""))
            for _, row in shown.iterrows():
                label = f"{row['Outlet']}  \n{row['Site']} · {row['Wilayah']}"
                st.button(
                    label,
                    key=f"pick_{list_type}_{row['Site']}",
                    use_container_width=True,
                    on_click=pick_outlet,
                    # HOREKA selalu pakai format With Keg secara default -- untuk UMUM
                    # flag ini otomatis diabaikan di bawah (want_keg = with_keg and
                    # q_type == "HOREKA"), jadi aman selalu True di sini.
                    args=(row["Site"], list_type, True),
                )
    else:
        st.caption("Ketik nama atau kode outlet untuk mulai mencari.")

if "last_query" in st.session_state:
    q_site, q_type, q_with_keg = st.session_state["last_query"]
    want_keg = q_with_keg and q_type == "HOREKA"

    with st.spinner(
        f"Memuat data {q_type} (~10 detik untuk pencarian pertama di grup ini, "
        "setelahnya jadi cepat selama app tidak di-restart)..."
    ):
        try:
            row_cells, info, cutoff = build_report_rows(q_site, q_type, want_keg)
        except ValueError:
            row_cells, info, cutoff = None, None, None

    if info is None:
        st.error(f"Site '{q_site}' tidak ditemukan di {q_type}.")
    else:
        st.subheader(info["Outlet"])
        meta_cols = st.columns(4)
        meta_cols[0].metric("Site", info["Site"])
        meta_cols[1].metric("Wilayah", info["Wilayah"])
        meta_cols[2].metric("Cut Off", cutoff or "-")
        meta_cols[3].metric("Kota", info["Kota"])
        st.caption(f"{info['Propinsi']} / {info['Kota']} / {info['Kecamatan']} / {info['Alamat']}")

        col_excel, _spacer, col_copyprint = st.columns([1.2, 2.3, 1.5])

        with col_excel:
            # Excel murni pakai openpyxl (bukan matplotlib) jadi tidak terpengaruh kalau
            # matplotlib gagal dimuat -- taruh di luar try/except Copy/Print di bawah.
            st.download_button(
                "Download Excel",
                build_report_excel(q_site, q_type, with_keg=want_keg),
                file_name=f"{info['Site']} {info['Outlet']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col_copyprint:
            # PNG disiapkan otomatis di belakang layar (bukan lewat tombol terpisah) --
            # cuma dipakai sebagai sumber untuk tombol Copy/Print, tidak ditampilkan besar
            # di halaman supaya tidak redundan dengan tabel di bawah. Di-cache per
            # (site, grup, with_keg) supaya tidak generate ulang tiap rerun Streamlit.
            # Dibungkus try/except supaya kalau matplotlib gagal dimuat (mis. diblokir
            # Windows Smart App Control), cuma Copy/Print yang mati -- bukan seluruh
            # halaman (pencarian & tabel tetap harus jalan).
            try:
                cache_key = (q_site, q_type, want_keg)
                if st.session_state.get("png_cache_key") != cache_key:
                    with st.spinner("Menyiapkan laporan untuk copy/print..."):
                        png_path = render_outlet_report(q_site, q_type, with_keg=want_keg)
                        with open(png_path, "rb") as f:
                            st.session_state["png_bytes"] = f.read()
                        st.session_state["png_cache_key"] = cache_key

                b64 = base64.b64encode(st.session_state["png_bytes"]).decode()
                components.html(
                    f"""
                <style>
                  .action-btn {{
                    display: inline-block; padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer;
                    border-radius: 0.5rem; border: 1px solid #999; margin-right: 0.5rem;
                    color: inherit; text-decoration: none; background: #f0f2f6;
                    font-family: inherit;
                  }}
                </style>
                <button class="action-btn" onclick="copyReportImage()">Copy to Clipboard</button>
                <a id="print-link" class="action-btn" href="#" target="_blank" rel="noopener noreferrer">Print</a>
                <span id="action-status" style="margin-left:0.5rem;"></span>
                <script>
                const reportImgSrc = "data:image/png;base64,{b64}";

                async function copyReportImage() {{
                    const status = document.getElementById('action-status');
                    status.textContent = 'Menyalin...';
                    try {{
                        const resp = await fetch(reportImgSrc);
                        const blob = await resp.blob();
                        await navigator.clipboard.write([new ClipboardItem({{'image/png': blob}})]);
                        status.textContent = 'Tersalin!';
                    }} catch (e) {{
                        status.textContent = 'Gagal copy (browser tidak mendukung) -- coba Chrome/Edge.';
                    }}
                }}

                // Print pakai <a target="_blank"> ke Blob URL, BUKAN window.open() --
                // window.open() dipanggil dari dalam iframe components.html() diblokir
                // popup-blocker browser (terbukti: user selalu dapat pesan "Gagal buka tab
                // print"). Navigasi <a> asli tidak kena heuristik popup-blocker yang sama,
                // jadi jauh lebih bisa diandalkan dari konteks iframe. href-nya (Blob URL)
                // disiapkan di sini, SEBELUM diklik, supaya klik-nya murni navigasi native.
                // Laporan itu satu gambar PNG utuh (bukan tabel HTML), jadi browser
                // TIDAK bisa memberi jeda halaman yang pas di batas baris -- kalau cuma
                // width:100%, gambar yang lebih tinggi dari 1 halaman kepotong PAS DI
                // TENGAH tabel waktu print. Percobaan pertama (skala pakai px hasil
                // tebakan JS) TERBUKTI masih meleset -- asumsi px/inch beda-beda per
                // browser/printer. Diganti pakai satuan FISIK (mm) yang diikat langsung
                // ke ukuran kertas @page -- ini yang dijamin konsisten oleh browser
                // untuk konteks print, tidak bergantung tebakan DPI sama sekali.
                // object-fit:contain di dalam kotak 287mm x 200mm (A4 landscape - margin
                // 5mm tiap sisi) MEMAKSA gambar (berapa pun ukuran piksel aslinya) untuk
                // selalu muat pas di satu halaman, tidak pernah lebih besar dari itu.
                const printHtml =
                    '<html><head><title>Print Laporan</title>' +
                    '<style>' +
                    '@page {{ size: landscape; margin: 5mm; }}' +
                    'html, body {{ margin:0; padding:0; height:100%; }}' +
                    '.print-page {{ width:287mm; height:200mm; display:flex; align-items:center; justify-content:center; }}' +
                    '.print-page img {{ max-width:100%; max-height:100%; object-fit:contain; }}' +
                    '</style>' +
                    '</head>' +
                    '<body>' +
                    '<div class="print-page"><img src="' + reportImgSrc + '" onload="window.print()"></div>' +
                    '</body></html>';
                const printBlob = new Blob([printHtml], {{type: 'text/html'}});
                document.getElementById('print-link').href = URL.createObjectURL(printBlob);
                </script>
                """,
                    height=50,
                )
            except Exception as e:
                st.warning(f"Copy/Print tidak tersedia: {e}")

        # Cutoff PER BRAND (bukan cuma satu tanggal untuk seluruh outlet) --
        # dibutuhkan karena brand yang beda bisa punya tanggal sync terakhir
        # yang beda juga (lihat pages/6_Cek_Cutoff_OMSHAR.py). get_cutoff_date()
        # di-cache lru_cache jadi baris brand yang sama tidak baca file berkali-kali.
        brand_cutoffs = {
            label: get_cutoff_date(brand=label, omshar_type=q_type)
            for label in {row[2] for row in row_cells}
        }
        st.markdown(build_html_table(row_cells, cutoffs=brand_cutoffs), unsafe_allow_html=True)

        gabungan_info = load_gabungan_map().get(q_site)
        if gabungan_info:
            children = gabungan_info["children"]
            with st.expander(f"Toko yang tergabung ({len(children)})"):
                child_idx = get_outlet_index(q_type)
                child_rows = child_idx[child_idx["Site"].isin(children)][["Site", "Outlet", "Wilayah"]]
                # Tidak semua toko anak pasti punya baris di brand BIR (sumber get_outlet_index)
                # -- kalau ada yang tidak ketemu, tetap tampilkan site code-nya supaya jumlah
                # yang muncul cocok dengan jumlah toko anak asli, bukan diam-diam hilang.
                missing = set(children) - set(child_rows["Site"])
                if missing:
                    child_rows = pd.concat([
                        child_rows,
                        pd.DataFrame([{"Site": s, "Outlet": "(data tidak ditemukan)", "Wilayah": "-"} for s in missing]),
                    ], ignore_index=True)
                st.dataframe(child_rows, use_container_width=True, hide_index=True)
