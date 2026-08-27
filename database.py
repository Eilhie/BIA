"""
database.py
Modul untuk koneksi SQLite, inisialisasi tabel, dan fungsi logging/audit trail.
Ditempatkan di root project (D:\\SDAAREA), berjalan berdampingan dengan app.py.
"""

import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path

# Path database - sesuai struktur folder DB/auth
DB_PATH = "DB/auth/access_log.db"


@contextmanager
def get_connection():
    """Context manager supaya koneksi selalu ditutup dengan benar,
    walau terjadi error di tengah proses."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Panggil sekali saat app.py start. Aman dipanggil berulang kali
    karena pakai CREATE TABLE IF NOT EXISTS."""
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                success INTEGER NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS account_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        ''')


def log_action(username: str, action: str, detail: str = ""):
    """Catat aksi user (buka halaman, export data, filter data, dsb)."""
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO access_log (timestamp, username, action, detail) VALUES (?, ?, ?, ?)',
            (str(datetime.now()), username, action, detail)
        )


def log_login_attempt(username: str, success: bool):
    """Catat setiap percobaan login, berhasil atau gagal.
    Penting untuk deteksi percobaan akses tidak sah."""
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO login_attempts (timestamp, username, success) VALUES (?, ?, ?)',
            (str(datetime.now()), username, int(success))
        )


def get_logs(limit: int = 200):
    """Ambil log terbaru, urut dari yang paling baru."""
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT timestamp, username, action, detail FROM access_log '
            'ORDER BY timestamp DESC LIMIT ?', (limit,)
        )
        return cursor.fetchall()


def get_login_attempts(limit: int = 200):
    """Ambil riwayat percobaan login terbaru."""
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT timestamp, username, success FROM login_attempts '
            'ORDER BY timestamp DESC LIMIT ?', (limit,)
        )
        return cursor.fetchall()


def get_logs_by_user(username: str, limit: int = 200):
    """Ambil log khusus satu user - berguna untuk audit spesifik."""
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT timestamp, action, detail FROM access_log '
            'WHERE username = ? ORDER BY timestamp DESC LIMIT ?',
            (username, limit)
        )
        return cursor.fetchall()


def query_logs(username: str = "", action: str = "", since: str = "", until: str = "",
                limit: int = 500):
    """Query access_log dengan filter opsional -- dipakai halaman Audit Trail
    supaya bisa telusuri trail SATU orang secara spesifik (query per user),
    bukan cuma scroll semua orang tercampur. Semua filter opsional (string
    kosong = tidak difilter); since/until dalam format yang sama dengan
    str(datetime.now()) supaya bisa dibandingkan langsung sebagai TEXT."""
    query = 'SELECT timestamp, username, action, detail FROM access_log WHERE 1=1'
    params = []
    if username:
        query += ' AND username = ?'
        params.append(username)
    if action:
        query += ' AND action = ?'
        params.append(action)
    if since:
        query += ' AND timestamp >= ?'
        params.append(since)
    if until:
        query += ' AND timestamp <= ?'
        params.append(until)
    query += ' ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall()


def get_distinct_actions() -> list:
    """Daftar jenis aksi yang pernah tercatat -- buat opsi filter di halaman
    Audit Trail (login, buka_halaman, cari_outlet, lihat_outlet, dsb)."""
    with get_connection() as conn:
        cursor = conn.execute('SELECT DISTINCT action FROM access_log ORDER BY action')
        return [r[0] for r in cursor.fetchall()]


def _filtered_count_query(select_expr: str, username: str, action: str, since: str, until: str) -> tuple[str, list]:
    """Bangun 'SELECT {select_expr}, COUNT(*) FROM access_log WHERE ... GROUP BY
    {select_expr}' dengan filter opsional -- dipakai bareng oleh summarize_*()
    di bawah supaya logika filter (username/action/rentang tanggal) konsisten
    satu tempat, sama seperti pola di query_logs()."""
    query = f'SELECT {select_expr}, COUNT(*) c FROM access_log WHERE 1=1'
    params: list = []
    if username:
        query += ' AND username = ?'
        params.append(username)
    if action:
        query += ' AND action = ?'
        params.append(action)
    if since:
        query += ' AND timestamp >= ?'
        params.append(since)
    if until:
        query += ' AND timestamp <= ?'
        params.append(until)
    query += f' GROUP BY {select_expr} ORDER BY c DESC'
    return query, params


def summarize_by_action(username: str = "", since: str = "", until: str = "") -> list[tuple[str, int]]:
    """[(jenis_aksi, jumlah)] -- 'page counter' per jenis aksi (buka_halaman,
    cari_outlet, lihat_outlet, dsb), diurutkan paling sering duluan."""
    query, params = _filtered_count_query("action", username, "", since, until)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def summarize_pages(username: str = "", since: str = "", until: str = "") -> list[tuple[str, int]]:
    """[(nama_halaman, jumlah)] -- berapa kali tiap halaman DIBUKA (action=
    'buka_halaman', detail-nya nama halaman) -- ini yang dimaksud 'page
    counter': siapa pun yang buka halaman apa, kehitung di sini."""
    query, params = _filtered_count_query("detail", username, "buka_halaman", since, until)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def summarize_users(action: str = "", since: str = "", until: str = "", limit: int = 20) -> list[tuple[str, int]]:
    """[(username, jumlah_aksi)] -- siapa paling aktif (opsional dibatasi ke
    satu jenis aksi, mis. 'cari_outlet' buat lihat siapa paling banyak
    mencari)."""
    query, params = _filtered_count_query("username", "", action, since, until)
    query += ' LIMIT ?'
    params.append(limit)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def count_events(username: str = "", action: str = "", since: str = "", until: str = "") -> int:
    """Total baris access_log yang cocok filter -- dipakai buat metric
    ringkasan ('X aksi tercatat dalam rentang ini')."""
    query = 'SELECT COUNT(*) FROM access_log WHERE 1=1'
    params: list = []
    if username:
        query += ' AND username = ?'
        params.append(username)
    if action:
        query += ' AND action = ?'
        params.append(action)
    if since:
        query += ' AND timestamp >= ?'
        params.append(since)
    if until:
        query += ' AND timestamp <= ?'
        params.append(until)
    with get_connection() as conn:
        return conn.execute(query, params).fetchone()[0]


def count_recent_failed_attempts(username: str, window_seconds: int = 300) -> int:
    """Hitung percobaan login GAGAL untuk satu username dalam window waktu
    terakhir (detik) -- dipakai auth.py untuk lockout sementara setelah
    beberapa kali salah, supaya brute-force password jadi lebih sulit."""
    since = str(datetime.now() - timedelta(seconds=window_seconds))
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT COUNT(*) FROM login_attempts '
            'WHERE username = ? AND success = 0 AND timestamp >= ?',
            (username, since)
        )
        return cursor.fetchone()[0]


def create_user(username: str, password_hash: str, level: int) -> None:
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO users (username, password_hash, level, active, created_at) '
            'VALUES (?, ?, ?, 1, ?)',
            (username, password_hash, level, str(datetime.now()))
        )


def get_user(username: str):
    """Return dict {username, password_hash, level, active} atau None kalau tidak ada."""
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT username, password_hash, level, active FROM users WHERE username = ?',
            (username,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {"username": row[0], "password_hash": row[1], "level": row[2], "active": bool(row[3])}


def list_users():
    """Return list of dict, urut username -- untuk halaman Kelola User."""
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT username, level, active, created_at FROM users ORDER BY username'
        )
        return [
            {"username": r[0], "level": r[1], "active": bool(r[2]), "created_at": r[3]}
            for r in cursor.fetchall()
        ]


def count_users() -> int:
    with get_connection() as conn:
        return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]


def set_user_level(username: str, level: int) -> None:
    with get_connection() as conn:
        conn.execute('UPDATE users SET level = ? WHERE username = ?', (level, username))


def set_user_active(username: str, active: bool) -> None:
    with get_connection() as conn:
        conn.execute('UPDATE users SET active = ? WHERE username = ?', (int(active), username))


def set_user_password(username: str, password_hash: str) -> None:
    with get_connection() as conn:
        conn.execute('UPDATE users SET password_hash = ? WHERE username = ?', (password_hash, username))


def create_session(token: str, username: str, expires_at_iso: str) -> None:
    """Simpan token login persisten (cookie 24 jam) -- lihat auth.py._start_session()."""
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)',
            (token, username, expires_at_iso)
        )


def get_session(token: str):
    """Return {'username', 'expires_at'} kalau token ada & belum lewat expires_at,
    None kalau token tidak ada/sudah expired (TIDAK menghapus baris expired di sini --
    lihat delete_expired_sessions() untuk itu, biar fungsi ini murni baca)."""
    with get_connection() as conn:
        cursor = conn.execute('SELECT username, expires_at FROM sessions WHERE token = ?', (token,))
        row = cursor.fetchone()
        if row is None:
            return None
        username, expires_at = row
        if datetime.now() > datetime.fromisoformat(expires_at):
            return None
        return {"username": username, "expires_at": expires_at}


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))


def delete_expired_sessions() -> None:
    """Bersihkan token yang sudah lewat masa berlaku -- dipanggil sekali saat
    auth.py di-import (per start proses Streamlit), bukan tiap request."""
    with get_connection() as conn:
        conn.execute('DELETE FROM sessions WHERE expires_at < ?', (str(datetime.now()),))


def create_account_request(username: str, password_hash: str, note: str = "") -> None:
    """User yang belum punya akun ajukan permintaan lewat form login -- masuk
    antrian 'pending', baru jadi akun sungguhan setelah Admin approve lewat
    halaman Kelola User (lihat approve_account_request())."""
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO account_requests (username, password_hash, note, status, created_at) '
            'VALUES (?, ?, ?, \'pending\', ?)',
            (username, password_hash, note, str(datetime.now()))
        )


def has_pending_request(username: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM account_requests WHERE username = ? AND status = 'pending'",
            (username,)
        )
        return cursor.fetchone()[0] > 0


def list_pending_requests():
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, username, password_hash, note, created_at FROM account_requests "
            "WHERE status = 'pending' ORDER BY created_at"
        )
        return [
            {"id": r[0], "username": r[1], "password_hash": r[2], "note": r[3], "created_at": r[4]}
            for r in cursor.fetchall()
        ]


def approve_account_request(request_id: int, level: int) -> None:
    """Bikin user sungguhan dari password yang SUDAH di-hash user itu sendiri
    saat request (Admin tidak pernah lihat/pegang password aslinya) -- Admin
    cuma menentukan level akses-nya."""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT username, password_hash FROM account_requests WHERE id = ?', (request_id,)
        ).fetchone()
        if row is None:
            return
        username, password_hash = row
        conn.execute(
            'INSERT INTO users (username, password_hash, level, active, created_at) '
            'VALUES (?, ?, ?, 1, ?)',
            (username, password_hash, level, str(datetime.now()))
        )
        conn.execute("UPDATE account_requests SET status = 'approved' WHERE id = ?", (request_id,))


def reject_account_request(request_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE account_requests SET status = 'rejected' WHERE id = ?", (request_id,))