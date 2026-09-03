"""
SYNC & TRANSPOSE
Halaman Streamlit untuk sync OMSHAR dari server + transpose jadi CSV/XLSX,
menggantikan SYNC OMSHAR FAST.bat + AMBIL DATA BARU.bat / omset_pipeline/RUN.bat.

Sync & Transpose jalan di background thread/subprocess + di-poll lewat
st.fragment(run_every=...) supaya bisa dibatalkan di tengah jalan -- kalau
loop baca output dibiarkan blocking di main script (seperti versi awal),
tombol Cancel tidak akan pernah terdaftar sampai operasinya selesai sendiri,
karena Streamlit cuma proses satu interaksi per waktu per sesi.
"""

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import omset_seeker
import sku_lookup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omset_pipeline"))
import transpose as _t  # noqa: E402 -- cuma buat jumlah brand per mode (progress bar)

SRC_SERVER = r"\\10.4.1.25\Bev\OMSHAR"
DEST_DB = r"D:\DB OMSHAR\DB"
SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")
TRANSPOSE_DIR = Path(__file__).resolve().parent.parent / "omset_pipeline"

# Total brand yang akan diproses per mode -- dipakai buat progress bar "X/Y brand".
# HOREKA dan "HOREKA + KEG/PET" sengaja dipisah jadi 2 mode (bukan selalu
# dibundel) -- pass KEG/PET tambahan itu brand ekstra yang tidak selalu
# dibutuhkan tiap transpose HOREKA.
_N_UMUM = len(_t.BRAND_ORDER)
_N_HOREKA_BASE = len(_t.BRAND_ORDER)
_N_HOREKA_KEG = len(_t.BRAND_ORDER) + len(_t.HOREKA_KEG_BRAND_ORDER)
TRANSPOSE_TOTALS = {
    "UMUM": _N_UMUM,
    "HOREKA": _N_HOREKA_BASE,
    "HOREKA + KEG/PET": _N_HOREKA_KEG,
    "ALL": _N_UMUM + _N_HOREKA_KEG,
}
# Label radio (UI) -> argumen CLI transpose.py
MODE_CLI_ARG = {
    "UMUM": "umum",
    "HOREKA": "horeka",
    "HOREKA + KEG/PET": "horeka_keg",
    "ALL": "all",
}


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}j {m}m {s}d"
    if m:
        return f"{m}m {s}d"
    return f"{s}d"

auth.require_level(5, page="Sync dan Transpose")
st.title("Sync & Transpose OMSHAR")


def _kill_process_tree(pid: int) -> None:
    """taskkill /T juga membunuh anak proses (mis. worker multiprocessing.Pool
    milik transpose.py) -- kalau cuma proc.terminate() pada proses induk, anak
    prosesnya bisa jadi orphan dan tetap jalan di background."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


# ── 1. SYNC ──────────────────────────────────────────────────────────────────
# Jalan di background thread (bukan subprocess tunggal) karena aslinya memang
# banyak panggilan robocopy pendek per brand -- cancel dicek DI ANTARA brand,
# bukan paksa hentikan robocopy yang lagi jalan (robocopy /MT:8 per brand
# biasanya cuma hitungan detik, jadi ini cukup responsif tanpa perlu rumit).

def _sync_worker(categories, log_queue, cancel_event, result):
    # [FIX] robocopy exit code SEBELUMNYA dibuang begitu saja -- cuma dicek
    # file-nya ADA atau tidak setelahnya. Itu buta terhadap kasus nyata: file
    # SUDAH ada dari sync HARI SEBELUMNYA, robocopy hari ini GAGAL menariknya
    # ulang (server lagi nulis file itu, network blip, dsb -- /R:1 /W:1 cuma
    # 1x percobaan), tapi karena file lama itu tetap ADA di disk, cek exists()
    # lolos dan Sync dilaporkan "lengkap" padahal isinya masih basi.
    # Robocopy exit code itu bitmask (lihat dokumentasi resmi): bit 0-2 (nilai
    # 0-7) semua varian SUKSES (0=tidak ada yang perlu disalin, 1=berhasil
    # disalin, 2=ada file extra, 4=mismatch, gabungan spt 3/5/7 tetap sukses).
    # Bit 3 (nilai 8) ke atas = robocopy GAGAL menyalin sebagian/semua file --
    # itu yang sekarang ditangkap sebagai error, terpisah dari 'missing'.
    all_missing = []
    all_sync_errors = []
    for category in categories:
        if cancel_event.is_set():
            log_queue.put(("line", f"[DIBATALKAN] Berhenti sebelum kategori {category}."))
            break
        list_dir = SKU_LIST_DIR / category
        if not list_dir.exists():
            log_queue.put(("line", f"[SKIP] {list_dir} tidak ditemukan."))
            continue
        cancelled_mid_category = False
        for txt in sorted(list_dir.glob("*.txt")):
            if cancel_event.is_set():
                log_queue.put(("line", f"[DIBATALKAN] Berhenti sebelum {category}/{txt.stem}."))
                cancelled_mid_category = True
                break
            skus = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
            if not skus:
                log_queue.put(("line", f"[WARN] [{category}] {txt.stem}: SKU list kosong, di-skip."))
                continue
            file_names = [f"OMSHAR {category} {s}.xls" for s in skus]
            log_queue.put(("line", f"[{category}] {txt.stem} ({len(file_names)} SKU)"))
            cmd = ["robocopy", SRC_SERVER, DEST_DB, *file_names,
                   "/XO", "/R:1", "/W:1", "/MT:8", "/NP", "/NDL", "/NJH", "/NJS"]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode >= 8:
                log_queue.put(("line", f"  [ROBOCOPY GAGAL] {category}/{txt.stem}: exit code {proc.returncode} -- lihat detail di bawah, file yang sudah ada BISA JADI masih versi lama."))
                tail = (proc.stdout or "").strip().splitlines()[-15:]
                for line in tail:
                    log_queue.put(("line", f"    {line}"))
                all_sync_errors.append({
                    "Grup": category, "Kategori": txt.stem,
                    "Exit code": proc.returncode, "Jumlah SKU di batch": len(file_names),
                })
            for fname in file_names:
                if not (Path(DEST_DB) / fname).exists():
                    all_missing.append({"Grup": category, "Kategori": txt.stem, "File": fname})
        if cancelled_mid_category:
            break
    result["missing"] = all_missing
    result["sync_errors"] = all_sync_errors
    log_queue.put(("done", None))


def _start_sync(categories: list[str]) -> None:
    q: queue.Queue = queue.Queue()
    cancel_event = threading.Event()
    result: dict = {}
    t = threading.Thread(target=_sync_worker, args=(categories, q, cancel_event, result), daemon=True)
    t.start()
    st.session_state["sync_state"] = {
        "thread": t, "queue": q, "cancel_event": cancel_event, "result": result,
        "lines": [], "finished": False, "cancelled": False,
    }


@st.fragment(run_every=1)
def _sync_progress():
    state = st.session_state.get("sync_state")
    if state is None:
        return

    while True:
        try:
            kind, payload = state["queue"].get_nowait()
        except queue.Empty:
            break
        if kind == "done":
            state["finished"] = True
        else:
            state["lines"].append(payload)

    st.code("\n".join(state["lines"][-40:]) or "(memulai...)")

    if state["finished"]:
        missing = state["result"].get("missing", [])
        sync_errors = state["result"].get("sync_errors", [])
        if state["cancelled"]:
            st.warning("Sync dibatalkan.")
        else:
            # sku_lookup.load_sku_raw() jalur cepatnya baca CSV hasil Transpose (lihat
            # cache-clear di bagian Transpose di bawah, itu titik utama invalidate-nya).
            # Tapi jalur fallback-nya (kalau CSV itu belum ada) baca .xls mentah DEST_DB
            # langsung -- jadi tetap perlu dibersihkan di sini juga supaya fallback itu
            # tidak diam-diam pakai file mentah versi SEBELUM sync ini.
            sku_lookup.load_sku_raw.cache_clear()
            if sync_errors:
                st.error(
                    f"Robocopy melaporkan GAGAL untuk {len(sync_errors)} batch -- file yang sudah "
                    f"ADA di batch itu BISA JADI masih versi lama (bukan berarti isinya sudah "
                    f"ter-update, exists() tidak cukup buat memastikan itu). Lihat log di atas "
                    f"buat detail robocopy per batch, atau coba Sync ulang."
                )
                st.dataframe(pd.DataFrame(sync_errors), use_container_width=True, hide_index=True)
            if missing:
                st.warning(f"Sync selesai dengan {len(missing)} SKU terlewat (file belum pernah ada sama sekali):")
                st.dataframe(pd.DataFrame(missing), use_container_width=True, hide_index=True)
            if not sync_errors and not missing:
                st.success("Sync selesai, semua SKU lengkap dan robocopy tidak melaporkan error.")
        if st.button("Tutup", key="sync_close"):
            del st.session_state["sync_state"]
            st.rerun()
    else:
        if st.button("Cancel Sync", key="sync_cancel"):
            state["cancel_event"].set()
            state["cancelled"] = True


st.header("1. Sync OMSHAR dari Server")
st.caption(f"Sumber: `{SRC_SERVER}`  →  Tujuan: `{DEST_DB}`")

if "sync_state" in st.session_state:
    _sync_progress()
else:
    col1, col2 = st.columns(2)
    sync_umum = col1.checkbox("UMUM", value=True)
    sync_horeka = col2.checkbox("HOREKA", value=True)

    if st.button("Mulai Sync", type="primary"):
        if not Path(r"\\10.4.1.25\Bev").exists():
            st.error("Server \\\\10.4.1.25\\Bev tidak dapat diakses. Cek VPN/jaringan.")
        else:
            categories = [c for c, on in [("UMUM", sync_umum), ("HOREKA", sync_horeka)] if on]
            if not categories:
                st.warning("Centang minimal satu grup.")
            else:
                _start_sync(categories)
                st.rerun()

st.divider()

# ── 2. TRANSPOSE ─────────────────────────────────────────────────────────────
st.header("2. Transpose jadi CSV/XLSX")
st.caption(f"Sumber dibaca dari `{DEST_DB}`, output ke `omset_pipeline\\output\\`.")


def _spawn_transpose(cli_args: list[str], mode_label: str, total_override: int | None = None) -> None:
    # PYTHONUNBUFFERED=1 wajib di env (bukan cuma flag -u ke proses utama) --
    # transpose.py jalanin multiprocessing.Pool, dan worker-nya di Windows di-spawn
    # sebagai proses python.exe baru yang cuma warisan ENV VAR dari induknya, bukan
    # argumen command-line -u. Tanpa ini, print() di dalam worker (progress per
    # brand) numpuk di buffer OS dan baru muncul pas proses exit atau buffer penuh --
    # kalau di-Cancel duluan, log-nya hilang tanpa jejak sama sekali.
    env = {**os.environ, "OMSHAR_DIR": DEST_DB, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-u", "transpose.py", *cli_args],
        cwd=str(TRANSPOSE_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        env=env,
    )
    q: queue.Queue = queue.Queue()

    def _reader():
        for line in proc.stdout:
            q.put(("line", line.rstrip()))
        q.put(("done", None))

    threading.Thread(target=_reader, daemon=True).start()
    state = {
        "proc": proc, "queue": q, "lines": [], "finished": False, "cancelled": False,
        "start_time": time.time(), "mode": mode_label,
    }
    if total_override is not None:
        state["total_override"] = total_override
    st.session_state["transpose_state"] = state


def _start_transpose(mode: str) -> None:
    _spawn_transpose([MODE_CLI_ARG[mode]], mode)


def _start_transpose_custom(omshar_type: str, codes: list[str]) -> None:
    """Transpose SKU INDIVIDUAL yang dipilih manual -- isolated dari mode
    UMUM/HOREKA/ALL di atas (lihat run_custom() di transpose.py), tidak
    mengubah brand rollup resmi apa pun. total_override dipakai karena
    jumlah SKU di sini dinamis (sebanyak yang dipilih user), bukan angka
    tetap dari TRANSPOSE_TOTALS."""
    _spawn_transpose(["custom", omshar_type, ",".join(codes)], "CUSTOM", total_override=len(codes))


def _list_all_skus(omshar_type: str) -> list[tuple[str, str]]:
    """(nama_grup, kode_sku) untuk SEMUA kode di SKU_LIST/omshar_type -- beda
    dari BRAND_GROUPS di Detail SKU Brand Besar yang cuma 7 grup brand besar,
    di sini semua grup/txt ikut supaya SKU manapun bisa dipilih buat di-cache."""
    out = []
    d = SKU_LIST_DIR / omshar_type
    if not d.exists():
        return out
    for txt in sorted(d.glob("*.txt")):
        codes = [l.strip() for l in txt.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        for code in codes:
            out.append((txt.stem, code))
    return out


def _brands_accounted_for(lines: list[str]) -> int:
    """Hitung brand yang SUDAH kelar diproses (berhasil, di-skip, atau gagal) --
    bukan cuma yang berhasil, biar hitungan X/Y tetap benar walau ada brand yang
    di-skip (file sumber tidak ada) atau gagal (lihat _brand_worker di transpose.py)."""
    markers = ("Tersimpan XLSX :", "[SKIP]", "[GAGAL]")
    return sum(1 for l in lines if any(m in l for m in markers))


def _read_steps_done(lines: list[str]) -> int:
    """Hitung baris "{brand} {sheet}: N baris" -- satu per (brand, grup) yang
    SUDAH selesai dibaca, ditulis LEBIH AWAL daripada 'Tersimpan XLSX :' (lihat
    process_brand() di transpose.py: tiap grup dibaca+ditulis dulu, baru XLSX-nya
    disimpan di akhir SETELAH SEMUA grup kelar). X/Y brand di atas sengaja tidak
    diubah jadi granular per-grup (perlu tahu persis berapa grup per brand per
    mode, gampang salah) -- ini cuma indikator TAMBAHAN biar kelihatan ada
    aktivitas nyata selama window "0/Y brand" yang bisa beberapa menit lamanya."""
    return sum(1 for l in lines if " baris" in l)


@st.fragment(run_every=1)
def _transpose_progress():
    state = st.session_state.get("transpose_state")
    if state is None:
        return

    while True:
        try:
            kind, payload = state["queue"].get_nowait()
        except queue.Empty:
            break
        if kind == "done":
            state["finished"] = True
        else:
            state["lines"].append(payload)

    # Timer + progress bar -- proses per-brand pertama biasanya butuh 1-2 menit
    # sebelum baris progress pertama muncul (baca .xls mentah itu sendiri lambat,
    # bukan bug), jadi timer+ETA di sini penting supaya kelihatan "masih jalan"
    # dan bukan "macet" selama window itu.
    elapsed = time.time() - state["start_time"]
    total = state.get("total_override") or TRANSPOSE_TOTALS.get(state.get("mode"), 0)
    done = _brands_accounted_for(state["lines"])
    if not state["finished"] and total:
        eta_txt = ""
        if done > 0:
            eta_sec = (elapsed / done) * (total - done)
            eta_txt = f" · estimasi sisa {_fmt_duration(eta_sec)}"
        st.caption(f"⏱ {_fmt_duration(elapsed)} berjalan · {done}/{total} brand selesai{eta_txt}")
        st.progress(min(done / total, 1.0))
        if done == 0:
            # Brand baru terhitung "selesai" di atas setelah SEMUA grupnya kelar dibaca
            # (lihat process_brand()) -- baca satu file mentah ~225 detik, jadi normal
            # X/Y masih 0 selama beberapa menit pertama. Indikator ini nunjukin aktivitas
            # NYATA yang sudah terjadi (tiap grup yang sudah kelar dibaca) selama window itu,
            # supaya tidak kelihatan macet padahal jalan.
            steps = _read_steps_done(state["lines"])
            if steps:
                st.caption(f"📄 {steps} langkah baca (per grup) sudah selesai -- brand pertama akan tercatat begitu SEMUA grupnya kelar.")
    else:
        st.caption(f"⏱ Total waktu: {_fmt_duration(elapsed)}")

    st.code("\n".join(state["lines"][-40:]) or "(memulai...)")

    if state["finished"]:
        proc = state["proc"]
        proc.wait()
        if state["cancelled"]:
            st.warning("Transpose dibatalkan.")
        elif proc.returncode == 0:
            # load_brand() di omset_seeker.py di-cache pakai functools.lru_cache TANPA
            # TTL/expiry + parquet disk cache di output/CACHE/ -- kalau tidak dibersihkan
            # di sini, pencarian outlet di halaman lain (dalam sesi yang sama) bisa
            # diam-diam tetap pakai data SEBELUM transpose ini. Ini titik yang paling
            # tepat buat invalidate.
            omset_seeker.clear_brand_cache()
            omset_seeker.load_gabungan_map.cache_clear()
            omset_seeker.load_horeka_gabungan_map.cache_clear()
            omset_seeker.get_cutoff_parts.cache_clear()
            # sku_lookup.load_sku_raw() jalur cepatnya baca CSV SKU_RAW yang baru saja
            # ditulis ulang oleh transpose.py ini -- titik invalidate utamanya di sini,
            # bukan di Sync (Sync cuma jaga-jaga buat jalur fallback baca .xls mentah).
            sku_lookup.load_sku_raw.cache_clear()
            st.cache_data.clear()  # get_outlet_index (sidebar) + SKU Manifest
            st.success("Transpose selesai, cache di-refresh.")
        else:
            st.error(f"Transpose gagal (exit code {proc.returncode}).")
        if st.button("Tutup", key="transpose_close"):
            del st.session_state["transpose_state"]
            st.rerun()
    else:
        if st.button("Cancel Transpose", key="transpose_cancel"):
            state["cancelled"] = True
            _kill_process_tree(state["proc"].pid)


if "transpose_state" in st.session_state:
    _transpose_progress()
else:
    mode = st.radio("Mode", ["UMUM", "HOREKA", "HOREKA + KEG/PET", "ALL"], horizontal=True)
    st.caption(
        f"HOREKA dasar = {_N_HOREKA_BASE} brand. \"HOREKA + KEG/PET\" menambah "
        f"{len(_t.HOREKA_KEG_BRAND_ORDER)} brand draft/keg tambahan (termasuk yang SKU-nya "
        f"belum disync -- otomatis di-skip sampai ada). Mode ALL selalu mencakup keduanya, "
        f"dan bisa makan waktu ~1.5-2 jam."
    )

    if st.button("Mulai Transpose", type="primary"):
        _start_transpose(mode)
        st.rerun()

    with st.expander("Transpose SKU individual (custom) -- di luar 59 brand rollup di atas"):
        st.caption(
            "Mode di atas cuma baca ~73 file mentah (yang terdaftar di UMUM_FILE/HOREKA_FILE/"
            "HOREKA_KEG_FILE, dipakai bangun 59 brand rollup resmi). SKU lain yang sudah disync "
            "tapi tidak masuk daftar itu (dipakai Detail SKU Brand Besar) baru dibaca cold saat "
            "dicari (~20-25 detik/SKU) -- pilih SKU di sini buat di-cache lebih dulu, isolated, "
            "tidak mengubah brand rollup resmi apa pun."
        )
        custom_type = st.radio("Channel", ["UMUM", "HOREKA"], horizontal=True, key="custom_type")
        all_skus = _list_all_skus(custom_type)
        sku_options = [f"{group} / {code}" for group, code in all_skus]
        picked = st.multiselect("Pilih SKU", sku_options, key="custom_skus")
        picked_codes = [p.split(" / ", 1)[1] for p in picked]

        if st.button("Transpose SKU Terpilih", disabled=not picked_codes):
            _start_transpose_custom(custom_type, picked_codes)
            st.rerun()
