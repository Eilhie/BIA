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

import auth
import database as db
from omset_seeker import build_outlet_index, get_cutoff_date, load_brand, load_gabungan_map
from render_outlet_image import (
    build_html_table,
    build_report_excel,
    build_report_rows,
    render_outlet_report,
)

current_user = auth.require_level(1, page="Omset Seeker")
st.title("OMSET Seeker")

MAX_LIST_RESULTS = 30


@st.cache_data(show_spinner=False, ttl="10m")
def get_outlet_index(omshar_type: str):
    """Wrapper cache Streamlit di atas omset_seeker.build_outlet_index() -- dipakai sidebar
    buat browse/search outlet. Di-cache karena UMUM sendiri ~72rb baris, HOREKA ~15rb --
    tidak mau di-dedup ulang tiap keystroke."""
    return build_outlet_index(omshar_type)


def pick_outlet(site: str, omshar_type: str, with_keg: bool, outlet_name: str, wilayah: str, search_term: str) -> None:
    st.session_state["last_query"] = (site, omshar_type, with_keg)
    detail = f"[{omshar_type}] {site} - {outlet_name} ({wilayah})"
    if search_term:
        detail += f" | dicari: '{search_term}'"
    db.log_action(st.session_state["auth_user"]["username"], "lihat_outlet", detail)


with st.sidebar:
    st.header("Daftar Outlet")
    list_type = st.radio("Grup", ["UMUM", "HOREKA"], horizontal=True, key="list_type")

    # Index outlet di-load SEKALI di sini (bukan cuma pas ada query teks) supaya
    # opsi filter Wilayah di bawah bisa langsung terisi -- aman karena sudah
    # di-cache 10 menit lewat get_outlet_index(), jadi biaya penuhnya cuma
    # kena sekali per grup per 10 menit, bukan tiap keystroke/rerun.
    with st.spinner(f"Memuat daftar outlet {list_type}..."):
        outlets = get_outlet_index(list_type)

    list_query = st.text_input("Cari nama/kode outlet", key="list_query", placeholder="ketik untuk mencari...")
    wilayah_options = sorted(outlets["Wilayah"].dropna().unique().tolist())
    wilayah_filter = st.multiselect("Filter Wilayah", wilayah_options, key=f"wilayah_filter_{list_type}")

    q = list_query.strip()
    if q or wilayah_filter:
        matches = outlets
        if q:
            ql = q.lower()
            matches = matches[
                matches["Outlet"].str.lower().str.contains(ql, na=False, regex=False)
                | matches["Site"].str.lower().str.contains(ql, na=False, regex=False)
            ]
        if wilayah_filter:
            matches = matches[matches["Wilayah"].isin(wilayah_filter)]
        n = len(matches)

        # Audit: catat pencarian (teks dan/atau filter wilayah) -- di-dedup per
        # kombinasi unik supaya rerun lain (mis. klik tombol outlet) yang tidak
        # benar-benar mengubah pencarian tidak ikut nge-log ulang.
        log_key = (list_type, q, tuple(sorted(wilayah_filter)))
        if st.session_state.get("_last_logged_search") != log_key:
            st.session_state["_last_logged_search"] = log_key
            detail = f"[{list_type}]"
            if q:
                detail += f" query='{q}'"
            if wilayah_filter:
                detail += f" wilayah={','.join(wilayah_filter)}"
            detail += f" -> {n} hasil"
            db.log_action(current_user["username"], "cari_outlet", detail)

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
                    args=(row["Site"], list_type, True, row["Outlet"], row["Wilayah"], q),
                )
    else:
        st.caption("Ketik nama/kode outlet, atau pilih wilayah, untuk mulai mencari.")

if "last_query" in st.session_state:
    q_site, q_type, q_with_keg = st.session_state["last_query"]
    want_keg = q_with_keg and q_type == "HOREKA"

    with st.spinner(f"Memuat data {q_type}..."):
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

        # PNG disiapkan lebih dulu (dipakai bareng oleh tombol Download Gambar
        # DAN Copy/Print di bawah) -- di-cache per (site, grup, with_keg)
        # supaya tidak generate ulang tiap rerun Streamlit. Dibungkus try/except
        # supaya kalau matplotlib gagal dimuat (mis. diblokir Windows Smart App
        # Control), cuma fitur gambar yang mati -- bukan seluruh halaman
        # (pencarian & tabel tetap harus jalan).
        png_bytes = None
        try:
            cache_key = (q_site, q_type, want_keg)
            if st.session_state.get("png_cache_key") != cache_key:
                with st.spinner("Menyiapkan gambar laporan..."):
                    # precomputed=row_cells yang sudah dihitung di atas -- tidak query
                    # ulang; bytes kembali langsung dari render (tanpa baca ulang file).
                    _, generated_png = render_outlet_report(
                        q_site, q_type, with_keg=want_keg,
                        precomputed=(row_cells, info, cutoff),
                    )
                    st.session_state["png_bytes"] = generated_png
                    st.session_state["png_cache_key"] = cache_key
            png_bytes = st.session_state["png_bytes"]
        except Exception as e:
            png_error = e

        col_excel, col_image, _spacer, col_copyprint = st.columns([1.2, 1.2, 1.1, 1.5])

        with col_excel:
            # Excel murni pakai openpyxl (bukan matplotlib) jadi tidak terpengaruh kalau
            # matplotlib gagal dimuat -- terpisah dari png_bytes di atas.
            # Bytes di-cache per (site, grup, with_keg) -- st.download_button mengevaluasi
            # argumennya tiap rerun, tanpa cache workbook openpyxl dibangun ulang terus.
            # precomputed=row_cells yang sudah dihitung di atas -- tidak query ulang.
            xlsx_cache_key = (q_site, q_type, want_keg)
            if st.session_state.get("xlsx_cache_key") != xlsx_cache_key:
                st.session_state["xlsx_bytes"] = build_report_excel(precomputed=(row_cells, info, cutoff))
                st.session_state["xlsx_cache_key"] = xlsx_cache_key
            st.download_button(
                "Download Excel",
                st.session_state["xlsx_bytes"],
                file_name=f"{info['Site']} {info['Outlet']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col_image:
            if png_bytes is not None:
                st.download_button(
                    "Download Gambar",
                    png_bytes,
                    file_name=f"{info['Site']} {info['Outlet']}.png",
                    mime="image/png",
                )

        with col_copyprint:
            try:
                if png_bytes is None:
                    raise png_error

                b64 = base64.b64encode(png_bytes).decode()
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

                // navigator.clipboard.write() CUMA jalan di "secure context" (https://
                // atau http://localhost) -- browser MEMBLOKIR total di akses LAN biasa
                // (http://<IP-lokal>:8501, persis mode CARI OUTLET (LAN).bat), bukan
                // soal browser tidak mendukung. Makanya kalau itu gagal/tidak ada,
                // fallback ke document.execCommand('copy') yang lebih tua -- API itu
                // TIDAK terikat aturan secure-context jadi masih bisa jalan di LAN,
                // dengan trik: taruh gambarnya di elemen contenteditable tersembunyi,
                // select elemennya, baru panggil execCommand('copy').
                async function copyReportImage() {{
                    const status = document.getElementById('action-status');
                    status.textContent = 'Menyalin...';
                    try {{
                        const resp = await fetch(reportImgSrc);
                        const blob = await resp.blob();
                        if (!(window.isSecureContext && navigator.clipboard && navigator.clipboard.write)) {{
                            throw new Error('clipboard-api-unavailable');
                        }}
                        await navigator.clipboard.write([new ClipboardItem({{'image/png': blob}})]);
                        status.textContent = 'Tersalin!';
                        return;
                    }} catch (e) {{
                        // lanjut ke fallback di bawah
                    }}

                    try {{
                        const ok = await copyImageLegacyFallback();
                        status.textContent = ok ? 'Tersalin!' : 'Gagal copy -- coba Print atau Download Excel.';
                    }} catch (e2) {{
                        status.textContent = window.isSecureContext
                            ? 'Gagal copy (browser tidak mendukung) -- coba Chrome/Edge, atau pakai Print/Download Excel.'
                            : 'Copy to Clipboard diblokir browser di akses LAN (http tanpa HTTPS) -- pakai Print atau Download Excel sebagai gantinya.';
                    }}
                }}

                function copyImageLegacyFallback() {{
                    return new Promise((resolve, reject) => {{
                        const container = document.createElement('div');
                        container.contentEditable = 'true';
                        container.style.position = 'fixed';
                        container.style.left = '-9999px';
                        const img = document.createElement('img');
                        img.onload = () => {{
                            document.body.appendChild(container);
                            container.appendChild(img);
                            const range = document.createRange();
                            range.selectNode(img);
                            const sel = window.getSelection();
                            sel.removeAllRanges();
                            sel.addRange(range);
                            let ok = false;
                            try {{
                                ok = document.execCommand('copy');
                            }} catch (e3) {{
                                ok = false;
                            }}
                            sel.removeAllRanges();
                            document.body.removeChild(container);
                            resolve(ok);
                        }};
                        img.onerror = () => reject(new Error('image-load-failed'));
                        img.src = reportImgSrc;
                    }});
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

                # Tombol "Copy to Clipboard" di atas pakai navigator.clipboard.write(),
                # yang browser TOTAL blokir di luar secure context (https:// atau
                # http://localhost) -- termasuk fallback execCommand('copy') ternyata
                # TIDAK cukup diandalkan untuk gambar di browser modern (terbukti:
                # masih gagal di akses LAN meski sudah ada fallback itu). Klik-kanan
                # native browser TIDAK tunduk pada aturan secure-context sama sekali
                # (itu aksi UI browser, bukan panggilan API dari script halaman), jadi
                # ini satu-satunya cara yang DIJAMIN selalu berhasil apa pun originnya.
                with st.popover("Salin Gambar (cara pasti berhasil di LAN)"):
                    st.caption(
                        "Tombol 'Copy to Clipboard' di atas bisa gagal kalau diakses lewat "
                        "jaringan kantor (LAN) -- itu batasan keamanan browser, bukan bug. "
                        "Klik kanan gambar di bawah ini, lalu pilih **'Copy image'** / "
                        "**'Salin gambar'** -- cara ini selalu berhasil di browser apa pun, "
                        "termasuk lewat LAN."
                    )
                    st.image(st.session_state["png_bytes"])
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

        gabungan_info = load_gabungan_map(q_type).get(q_site)
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
