"""
auth.py
Login gate + kontrol akses berbasis level (0-5) untuk semua halaman Streamlit.

Panggil auth.require_level(N, page="Nama Halaman") di baris PALING ATAS tiap
halaman/entry point (sebelum elemen UI lain dirender) -- kalau session belum
login, tampilkan form login (atau setup akun Admin pertama kalau belum ada
user sama sekali); kalau level user kurang dari N, tolak akses dengan pesan
jelas. Password di-hash pakai bcrypt, tidak pernah disimpan/ditampilkan plain.

Blok "Halo, {username} / Logout" dirender otomatis di AREA UTAMA tiap halaman
(bukan sidebar), tepat sebelum st.title() halaman itu, sebagai bagian dari
require_level() -- tidak perlu panggilan terpisah.

Login bertahan 24 jam lewat cookie browser (token acak, divalidasi ke tabel
sessions di SQLite) -- supaya user tidak perlu login ulang tiap kali app
di-restart (mis. lewat .bat launcher) selama masih dalam hari yang sama.
Session di server (st.session_state) memang selalu hilang saat proses
Streamlit restart, makanya persistensi login HARUS lewat sisi client (cookie),
bukan cuma session_state.
"""

import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import extra_streamlit_components as stx
import streamlit as st
import yaml

import database as db

db.init_db()
db.delete_expired_sessions()

CONFIG_PATH = Path(__file__).parent / "config" / "config.yaml"
_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
LEVEL_LABELS = {int(k): v for k, v in _config.get("levels", {}).items()}
PAGE_LEVELS = _config.get("pages", {})

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_SEC = 300  # 5 menit

SESSION_COOKIE = "sda_session_token"
SESSION_LIFETIME_HOURS = 24


def level_label(level: int) -> str:
    return LEVEL_LABELS.get(level, "")


def level_display(level: int) -> str:
    """'Level N' polos, atau 'Level N - Label' kalau level itu punya title
    di config.yaml (saat ini cuma level 5 -- 'Admin' -- yang punya)."""
    label = level_label(level)
    return f"Level {level} - {label}" if label else f"Level {level}"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _cookie_manager() -> stx.CookieManager:
    # Konstruksi CookieManager() itu sendiri langsung memanggil komponen
    # "getAll" dengan key tetap -- kalau dipanggil 2x dalam SATU run (mis.
    # sekali baca buat restore-dari-cookie, sekali lagi tulis saat login
    # sukses di run yang sama), Streamlit menolak dengan
    # StreamlitDuplicateElementKey karena dua elemen ber-key sama di run
    # yang sama. Cache SATU instance per sesi browser (di session_state,
    # bertahan lintas rerun) supaya konstruksi cuma terjadi sekali --
    # .get()/.set()/.delete() sendiri tetap live call ke frontend tiap
    # dipanggil, jadi caching ini tidak bikin datanya basi.
    if "_cookie_manager" not in st.session_state:
        st.session_state["_cookie_manager"] = stx.CookieManager(key="sda_cookie_manager")
    return st.session_state["_cookie_manager"]


def _start_session(username: str, level: int):
    """Set session_state DAN cookie 24 jam -- dipanggil sekali saat login
    berhasil supaya browser masih ingat login ini walau app di-restart."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=SESSION_LIFETIME_HOURS)
    db.create_session(token, username, str(expires))
    st.session_state["auth_user"] = {"username": username, "level": level}
    st.session_state["auth_token"] = token
    _cookie_manager().set(cookie=SESSION_COOKIE, val=token, expires_at=expires, key="set_session_cookie")


def _end_session():
    token = st.session_state.get("auth_token")
    if token:
        db.delete_session(token)
    _cookie_manager().delete(cookie=SESSION_COOKIE, key="del_session_cookie")
    st.session_state.pop("auth_user", None)
    st.session_state.pop("auth_token", None)


def _try_restore_from_cookie():
    """Kalau session_state kosong (mis. baru buka tab/app baru) tapi browser
    masih bawa cookie token yang valid & belum expired, login otomatis --
    tanpa ini, user harus login ulang tiap kali proses Streamlit restart."""
    if "auth_user" in st.session_state:
        return
    token = _cookie_manager().get(cookie=SESSION_COOKIE)
    if not token:
        return
    sess = db.get_session(token)
    if sess is None:
        return
    user = db.get_user(sess["username"])
    if user is None or not user["active"]:
        return
    st.session_state["auth_user"] = {"username": user["username"], "level": user["level"]}
    st.session_state["auth_token"] = token


def _bootstrap_admin_form():
    """Tampil HANYA kalau belum ada user sama sekali -- buat akun Admin
    (level 5) pertama. Setelah itu user berikutnya dibuat lewat halaman
    Kelola User (level 5), bukan lewat layar ini lagi."""
    st.title("Setup Awal - Buat Akun Admin")
    st.caption(
        "Belum ada akun sama sekali di sistem ini. Buat akun Admin (level 5) "
        "pertama untuk login dan mengelola akun user lain nanti."
    )
    with st.form("bootstrap_form"):
        username = st.text_input("Username Admin")
        password = st.text_input("Password", type="password")
        password2 = st.text_input("Ulangi Password", type="password")
        submitted = st.form_submit_button("Buat Akun Admin", type="primary")

    if submitted:
        if not username.strip() or not password:
            st.error("Username dan password wajib diisi.")
        elif password != password2:
            st.error("Password dan ulangi password tidak sama.")
        elif len(password) < 6:
            st.error("Password minimal 6 karakter.")
        else:
            db.create_user(username.strip(), _hash_password(password), 5)
            db.log_action(username.strip(), "buat_akun_admin_pertama", "")
            st.success("Akun Admin berhasil dibuat. Silakan login.")
            time.sleep(1)
            st.rerun()
    st.stop()


def _login_form():
    st.title("Login")
    st.caption("Masuk untuk mengakses OMSET Seeker dan tools terkait. Login bertahan 24 jam di browser ini.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Masuk", type="primary")

    if submitted:
        uname = username.strip()
        if db.count_recent_failed_attempts(uname, LOCKOUT_WINDOW_SEC) >= MAX_LOGIN_ATTEMPTS:
            st.error(
                f"Terlalu banyak percobaan gagal untuk username ini. "
                f"Coba lagi dalam beberapa menit."
            )
            db.log_login_attempt(uname, False)
        else:
            user = db.get_user(uname)
            if user and user["active"] and _check_password(password, user["password_hash"]):
                db.log_login_attempt(uname, True)
                db.log_action(uname, "login", "")
                _start_session(user["username"], user["level"])
                st.rerun()
            else:
                db.log_login_attempt(uname, False)
                if user and not user["active"]:
                    st.error("Akun ini sudah dinonaktifkan. Hubungi Admin.")
                else:
                    st.error("Username atau password salah.")

    with st.expander("Belum punya akun? Request di sini"):
        st.caption(
            "Isi username dan password yang Anda inginkan -- setelah disetujui Admin "
            "(lihat halaman Kelola User), langsung bisa login pakai password ini juga, "
            "tidak perlu tanya password ke siapa pun."
        )
        with st.form("request_account_form", clear_on_submit=True):
            req_username = st.text_input("Username", key="req_username")
            req_password = st.text_input("Password", type="password", key="req_password")
            req_password2 = st.text_input("Ulangi Password", type="password", key="req_password2")
            req_note = st.text_input("Untuk keperluan apa? (opsional)", key="req_note")
            req_submitted = st.form_submit_button("Kirim Request")

        if req_submitted:
            ru = req_username.strip()
            if not ru or not req_password:
                st.error("Username dan password wajib diisi.")
            elif req_password != req_password2:
                st.error("Password dan ulangi password tidak sama.")
            elif len(req_password) < 6:
                st.error("Password minimal 6 karakter.")
            elif db.get_user(ru) is not None:
                st.error(f"Username '{ru}' sudah dipakai. Coba username lain.")
            elif db.has_pending_request(ru):
                st.warning(f"Sudah ada request pending untuk username '{ru}' -- tunggu Admin memproses.")
            else:
                db.create_account_request(ru, _hash_password(req_password), req_note.strip())
                st.success("Request terkirim. Hubungi Admin untuk mempercepat approval kalau perlu.")
    st.stop()


def _render_user_bar(user: dict):
    """Render di AREA UTAMA (bukan sidebar) di baris paling atas tiap halaman,
    sebelum st.title() halaman itu sendiri -- sengaja bukan di sidebar karena
    posisinya selalu terasa aneh di sana (nempel di bawah nav, jauh dari nav
    di scroll panjang, dsb)."""
    c1, c2 = st.columns([6, 1])
    c1.caption(f"Halo, **{user['username']}** ({level_display(user['level'])})")
    if c2.button("Logout", key="auth_logout_btn"):
        db.log_action(user["username"], "logout", "")
        _end_session()
        st.rerun()
    st.divider()


def get_current_user() -> dict:
    """Panggil di ENTRY POINT (app.py) SEBELUM membangun st.navigation() --
    pastikan sudah ada user yang login (tampilkan login/setup-admin-pertama
    kalau belum), TANPA cek level tertentu -- itu urusan require_level() per
    halaman dan filter daftar nav di app.py (biar menu yang tidak boleh
    diakses user memang tidak pernah muncul, bukan cuma diblokir pas diklik).
    Aman dipanggil berkali-kali per run (mis. app.py lalu require_level() di
    halaman aktif) -- cookie manager sudah di-cache per sesi, tidak dobel."""
    _try_restore_from_cookie()

    if "auth_user" not in st.session_state:
        if db.count_users() == 0:
            _bootstrap_admin_form()
        else:
            _login_form()
        raise RuntimeError("unreachable")  # st.stop() di atas selalu jalan lebih dulu

    return st.session_state["auth_user"]


def require_level(min_level: int, page: str = ""):
    """Panggil di baris paling atas tiap halaman. Return dict user kalau lolos,
    kalau tidak lolos halaman dihentikan (st.stop()) di dalam fungsi ini.
    Tetap dicek di sini (bukan cuma mengandalkan menu yang disembunyikan di
    app.py) sebagai lapis pertahanan kedua -- jaga-jaga kalau halaman diakses
    langsung lewat URL yang harusnya tidak terlihat di menu user itu."""
    user = get_current_user()

    if user["level"] < min_level:
        _render_user_bar(user)
        st.error(
            f"Akses ditolak. Halaman ini butuh level minimal {min_level} "
            f"({level_display(min_level)}), akun Anda {level_display(user['level'])}. "
            f"Hubungi Admin kalau butuh akses lebih tinggi."
        )
        st.stop()

    if page:
        db.log_action(user["username"], "buka_halaman", page)
    _render_user_bar(user)
    return user
