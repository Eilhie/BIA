"""
HOME
Landing page baru (menggantikan Omset Seeker sebagai default) -- level akses
1, semua user aktif bisa buka. Fokus: Player Progress (rank/XP/streak dari
access_log yang SUDAH ada, opt-in leaderboard), bukan halaman teknis seperti
Dashboard (tetap level akses 5/Admin, tidak berubah).

PENTING: "rank" gamifikasi di sini SENGAJA bukan "level" -- "level" di app
ini sudah berarti peran akses (0-5, lihat auth.py/config.yaml, "Level 5 =
Admin"). Menyebutnya "Level" juga di sini bikin dua konsep yang sama sekali
beda (peran akses vs keaktifan pakai app) kelihatan seperti hal yang sama,
di halaman yang sama pula.

XP dihitung dari aksi yang SUDAH tercatat hari ini juga (login, cari_outlet,
lihat_outlet, buka_halaman) -- tidak ada instrumentasi baru, lihat
database.py (XP_WEIGHTS, compute_xp, xp_to_rank, login_streak_days).
"""

import streamlit as st

import auth
import database as db

user = auth.require_level(1, page="Home")
username = user["username"]

st.title(f"Halo, {username}")

# ── Player Progress ───────────────────────────────────────────────────────
counts = db.get_user_action_counts(username)
xp = db.compute_xp(counts)
rank, xp_into, xp_needed = db.xp_to_rank(xp)
streak = db.login_streak_days(username)

p1, p2, p3 = st.columns([1, 2, 1])
with p1:
    st.markdown(
        f"<div style='font-size:34px; font-weight:700; line-height:1.2; text-align:center;'>{rank}</div>"
        f"<div style='text-align:center; color:gray; font-size:12px;'>{xp} XP total</div>",
        unsafe_allow_html=True,
    )
with p2:
    st.write("")
    if xp_needed is None:
        st.progress(1.0)
        st.caption(f"Rank tertinggi -- {xp} XP")
    else:
        st.progress(min(xp_into / xp_needed, 1.0))
        st.caption(f"{xp_into} / {xp_needed} XP menuju rank berikutnya")
with p3:
    st.metric("Login streak", f"{streak} hari" if streak else "belum mulai")

st.caption(
    "XP didapat dari pemakaian sehari-hari: login (+5), cari outlet (+2), lihat outlet (+3), "
    "buka halaman laporan (+5) -- semua sudah tercatat otomatis, tidak perlu tindakan tambahan."
)

st.divider()

# ── Opt-in leaderboard ───────────────────────────────────────────────────────
lb_col1, lb_col2 = st.columns([4, 1])
lb_col1.subheader("Papan Peringkat")
opted_in = db.get_leaderboard_opt_in(username)
new_opt_in = lb_col2.checkbox("Tampilkan saya", value=opted_in, key="lb_opt_in")
if new_opt_in != opted_in:
    db.set_leaderboard_opt_in(username, new_opt_in)
    st.rerun()

if not new_opt_in:
    st.caption("Kamu tidak muncul di papan peringkat sampai dicentang -- bukan sekadar disamarkan, benar-benar tidak ditampilkan.")

all_counts = db.get_all_users_action_counts()
board_rows = []
for uname, uc in all_counts.items():
    if not db.get_leaderboard_opt_in(uname):
        continue
    u_xp = db.compute_xp(uc)
    u_rank, _, _ = db.xp_to_rank(u_xp)
    board_rows.append((uname, u_rank, u_xp))
board_rows.sort(key=lambda r: r[2], reverse=True)

if not board_rows:
    st.info("Belum ada yang mengaktifkan papan peringkat.")
else:
    for i, (uname, u_rank, u_xp) in enumerate(board_rows, start=1):
        highlight = " **(kamu)**" if uname == username else ""
        st.write(f"{i}. **{uname}**{highlight} — {u_rank} · {u_xp} XP")

st.divider()

# ── Quick links ───────────────────────────────────────────────────────────
st.subheader("Mulai Cepat")
q1, q2 = st.columns(2)
with q1:
    st.page_link("omset_search_app.py", label="Cari Outlet (Omset Seeker)", icon="🔍")
with q2:
    st.page_link("pages/3_Cek_Klaim_SKU.py", label="Cek Klaim SKU", icon="📋")
