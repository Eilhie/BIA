"""
HOME
Landing page baru (menggantikan Omset Seeker sebagai default) -- level akses
1, semua user aktif bisa buka. Fokus: Player Progress (level/XP dari
access_log yang SUDAH ada, opt-in leaderboard), bukan halaman teknis seperti
Dashboard (tetap level akses 5/Admin, tidak berubah).

"Level" di sini AMAN dipakai lagi (bukan "rank") -- auth.py._render_user_bar()
sekarang tidak lagi menampilkan angka Level RBAC di bar umum tiap halaman
(cuma label peran, mis. "Admin"), jadi "Level" di seluruh app sekarang cuma
berarti satu hal buat user: progres gamifikasi, seperti level di game.

XP dihitung dari aksi yang SUDAH tercatat hari ini juga (login, cari_outlet,
lihat_outlet, buka_halaman) -- tidak ada instrumentasi baru, lihat
database.py (XP_WEIGHTS, compute_xp, xp_to_level).
"""

import streamlit as st

import auth
import database as db

user = auth.require_level(1, page="Home")
username = user["username"]

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=JetBrains+Mono:wght@500;600;700&display=swap">
    <style>
      .pp-card {
        border: 1px solid rgba(120,110,90,0.22);
        border-radius: 10px;
        background: linear-gradient(180deg, rgba(200,134,42,0.06), rgba(200,134,42,0.015));
        padding: 22px 26px;
        display: flex;
        align-items: center;
        gap: 24px;
        flex-wrap: wrap;
      }
      .pp-dial { width: 108px; height: 108px; position: relative; flex: none; }
      .pp-dial svg { width: 100%; height: 100%; }
      .pp-dial .lvl {
        position: absolute; inset: 0; display: flex; flex-direction: column;
        align-items: center; justify-content: center;
      }
      .pp-dial .lvl .n {
        font-family: 'Bebas Neue', Impact, sans-serif; font-size: 38px;
        line-height: 1; color: #c8862a;
      }
      .pp-dial .lvl .l { font-size: 9.5px; letter-spacing: 0.08em; opacity: 0.6; text-transform: uppercase; }
      .pp-info { flex: 1; min-width: 220px; }
      .pp-info .xp-total {
        font-family: 'JetBrains Mono', monospace; font-size: 13px; opacity: 0.75; margin-bottom: 6px;
      }
      .pp-bar-track { height: 10px; border-radius: 999px; background: rgba(120,110,90,0.18); overflow: hidden; }
      .pp-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #c8862a, #e0a447); }
      .pp-bar-caption { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; opacity: 0.65; margin-top: 6px; }

      .lb-row {
        display: grid; grid-template-columns: 34px 1fr auto auto; gap: 14px; align-items: center;
        padding: 9px 12px; border-radius: 7px;
      }
      .lb-row.me { background: rgba(63,125,92,0.12); }
      .lb-rank { font-family: 'JetBrains Mono', monospace; font-weight: 700; opacity: 0.55; text-align: center; }
      .lb-rank.top1 { color: #c8862a; opacity: 1; }
      .lb-name { font-weight: 600; font-size: 14px; }
      .lb-pill {
        font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600;
        padding: 2px 9px; border-radius: 999px; background: rgba(200,134,42,0.15); color: #c8862a;
        white-space: nowrap;
      }
      .lb-xp {
        font-family: 'JetBrains Mono', monospace; font-size: 12.5px; opacity: 0.7;
        font-variant-numeric: tabular-nums; text-align: right; min-width: 70px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"Halo, {username}")

# ── Player Progress ───────────────────────────────────────────────────────
counts = db.get_user_action_counts(username)
xp = db.compute_xp(counts)
level, xp_into, xp_needed = db.xp_to_level(xp)
frac = min(xp_into / xp_needed, 1.0) if xp_needed else 1.0

# Naik level TERDETEKSI di sini (bukan cuma dihitung ulang) -- last_seen_level
# tersimpan di DB (bukan session_state) supaya tetap kedeteksi biar pun user
# baru buka Home lagi besok/di device lain, bukan cuma dalam sesi yang sama.
last_seen_level = db.get_and_bump_last_seen_level(username, level)
if level > last_seen_level:
    st.balloons()
    st.success(f"Naik ke Level {level}! Terus pakai app buat naik lagi.")

circumference = 2 * 3.14159 * 46
offset = circumference * (1 - frac)
xp_display = f"{xp:,}".replace(",", ".")  # format Indonesia: titik ribuan

st.markdown(
    f"""
    <div class="pp-card">
      <div class="pp-dial">
        <svg viewBox="0 0 108 108" role="img" aria-label="Level {level}, {int(frac*100)} persen menuju level berikutnya">
          <circle cx="54" cy="54" r="46" fill="none" stroke="rgba(120,110,90,0.18)" stroke-width="10"></circle>
          <circle cx="54" cy="54" r="46" fill="none" stroke="#c8862a" stroke-width="10" stroke-linecap="round"
                  stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
                  transform="rotate(-90 54 54)"></circle>
        </svg>
        <div class="lvl"><div class="n">{level}</div><div class="l">Level</div></div>
      </div>
      <div class="pp-info">
        <div class="xp-total">{xp_display} XP total</div>
        <div class="pp-bar-track"><div class="pp-bar-fill" style="width:{frac*100:.0f}%;"></div></div>
        <div class="pp-bar-caption">{xp_into} / {xp_needed} XP menuju Level {level + 1}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "XP didapat dari pemakaian sehari-hari: login (+5), cari outlet (+2), lihat outlet (+3), "
    "buka halaman laporan (+5) -- semua sudah tercatat otomatis, tidak perlu tindakan tambahan."
)

st.divider()

# ── Leaderboard -- semua user aktif, TIDAK opt-in ────────────────────────────
# Sebelumnya opt-in (checkbox "Tampilkan saya") -- diubah atas permintaan
# eksplisit: semua user aktif tampil otomatis, tidak perlu tindakan apa pun.
# leaderboard_opt_in column & get_leaderboard_opt_in()/set_leaderboard_opt_in()
# di database.py SENGAJA dibiarkan ada (tidak dipakai lagi di sini) -- murah
# disimpan, gampang dipasang lagi kalau opt-in mau diaktifkan ulang nanti.
#
# Periode DIPISAH dari Level pribadi di atas (yang tetap XP SEMUA WAKTU, kayak
# level karakter game -- tidak masuk akal reset). Leaderboard "Semua Waktu"
# saja bikin akun yang paling lama/paling sering dipakai (mis. akun admin)
# permanen di posisi 1 selamanya -- tidak ada yang bisa nyusul, jadi tidak
# ada gunanya sebagai kompetisi. Mingguan/bulanan reset di jadwal TETAP
# (Senin/tanggal 1, lihat leaderboard_period_bounds()), jadi semua orang
# benar-benar mulai dari nol bareng-bareng tiap periode baru.
st.subheader("Papan Peringkat")

period_label = st.radio(
    "Periode", ["Minggu Ini", "Bulan Ini", "Semua Waktu"], index=0,
    horizontal=True, key="lb_period", label_visibility="collapsed",
)
period_key = {"Minggu Ini": "weekly", "Bulan Ini": "monthly", "Semua Waktu": "all"}[period_label]
since = db.leaderboard_period_bounds(period_key)

# Level badge di papan = level SEMUA WAKTU (identitas permanen, sama seperti
# badge pribadi di atas) -- yang berubah per periode cuma XP yang dipakai
# buat URUTAN peringkat. Roster = SEMUA user AKTIF (list_users(), bukan
# opted_in_users() lagi), supaya yang belum pernah pakai app periode ini
# tetap tampil (0 XP), tidak diam-diam hilang.
period_counts = db.get_all_users_action_counts(since=since)
alltime_counts = period_counts if not since else db.get_all_users_action_counts()

board_rows = []
for u in db.list_users():
    if not u["active"]:
        continue
    uname = u["username"]
    period_xp = db.compute_xp(period_counts.get(uname, {}))
    overall_xp = db.compute_xp(alltime_counts.get(uname, {}))
    overall_level, _, _ = db.xp_to_level(overall_xp)
    board_rows.append((uname, overall_level, period_xp))
board_rows.sort(key=lambda r: r[2], reverse=True)

if not board_rows:
    st.info("Belum ada user aktif.")
else:
    st.caption(f"Diurutkan berdasarkan XP {period_label.lower()} -- badge Lv. tetap level semua waktu.")
    rows_html = []
    for i, (uname, u_level, u_xp) in enumerate(board_rows, start=1):
        is_me = uname == username
        rank_class = "lb-rank top1" if i == 1 else "lb-rank"
        row_class = "lb-row me" if is_me else "lb-row"
        name = f"{uname} (kamu)" if is_me else uname
        u_xp_display = f"{u_xp:,}".replace(",", ".")
        rows_html.append(
            f'<div class="{row_class}"><div class="{rank_class}">{i}</div>'
            f'<div class="lb-name">{name}</div>'
            f'<div class="lb-pill">Lv.{u_level}</div>'
            f'<div class="lb-xp">{u_xp_display} XP</div></div>'
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)

st.divider()

# ── Quick links ───────────────────────────────────────────────────────────
st.subheader("Mulai Cepat")
q1, q2 = st.columns(2)
with q1:
    st.page_link("omset_search_app.py", label="Cari Outlet (Omset Seeker)", icon="🔍")
with q2:
    st.page_link("pages/3_Cek_Klaim_SKU.py", label="Cek Klaim SKU", icon="📋")
