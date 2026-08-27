"""
AUDIT TRAIL
Halaman khusus level 5 (Admin) -- log akses (buka halaman, cari outlet, lihat
outlet, dsb) dan riwayat percobaan login, TERPISAH dari Kelola User supaya
bisa fokus telusuri satu orang (query per user) tanpa harus scroll campur
dengan form kelola akun.
"""

from datetime import datetime, time as dtime

import pandas as pd
import streamlit as st

import auth
import database as db

auth.require_level(5, page="Audit Trail")
st.title("Audit Trail")
st.caption(
    "Log aksi tiap user (buka halaman, cari outlet, lihat outlet di Omset Seeker, "
    "perubahan akun, dsb) dan riwayat percobaan login. Pilih user di bawah untuk "
    "menelusuri trail satu orang secara spesifik."
)

users = db.list_users()
usernames = ["(Semua User)"] + [u["username"] for u in users]

col1, col2 = st.columns([1, 2])
selected_user = col1.selectbox("User", usernames, key="audit_user_filter")
actions = db.get_distinct_actions()
selected_actions = col2.multiselect("Filter Aksi (kosongkan = semua)", actions, key="audit_action_filter")

with st.expander("Filter tanggal (opsional)", expanded=False):
    dc1, dc2 = st.columns(2)
    date_from = dc1.date_input("Dari tanggal", value=None, key="audit_date_from")
    date_to = dc2.date_input("Sampai tanggal", value=None, key="audit_date_to")

username_filter = "" if selected_user == "(Semua User)" else selected_user
since = str(datetime.combine(date_from, dtime.min)) if date_from else ""
until = str(datetime.combine(date_to, dtime.max)) if date_to else ""

st.divider()

st.subheader("Ringkasan Aktivitas")
st.caption(
    "Page counter & ringkasan pencarian -- ikut filter user/tanggal di atas. Kosongkan filter "
    "user untuk lihat ringkasan SEMUA orang sekaligus."
)

total_events = db.count_events(username=username_filter, since=since, until=until)
search_count = db.count_events(username=username_filter, action="cari_outlet", since=since, until=until)
view_count = db.count_events(username=username_filter, action="lihat_outlet", since=since, until=until)
sm1, sm2, sm3 = st.columns(3)
sm1.metric("Total aksi tercatat", total_events)
sm2.metric("Total pencarian outlet", search_count)
sm3.metric("Total outlet dilihat", view_count)

col_pages, col_side = st.columns(2)
with col_pages:
    st.caption("**Halaman paling sering dibuka** (page counter)")
    pages = db.summarize_pages(username=username_filter, since=since, until=until)
    if pages:
        st.bar_chart(pd.DataFrame(pages, columns=["Halaman", "Jumlah"]).set_index("Halaman"))
    else:
        st.caption("Belum ada data.")

with col_side:
    if username_filter:
        st.caption(f"**Rincian jenis aksi -- {username_filter}**")
        actions = db.summarize_by_action(username=username_filter, since=since, until=until)
        cols = ["Aksi", "Jumlah"]
    else:
        st.caption("**User paling aktif**")
        actions = db.summarize_users(since=since, until=until)
        cols = ["User", "Jumlah Aksi"]
    if actions:
        st.bar_chart(pd.DataFrame(actions, columns=cols).set_index(cols[0]))
    else:
        st.caption("Belum ada data.")

st.divider()

if username_filter:
    u_info = next((u for u in users if u["username"] == username_filter), None)
    recent_login = db.query_logs(username=username_filter, action="login", limit=1)
    st.subheader(f"Ringkasan -- {username_filter}")
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Level saat ini", auth.level_display(u_info["level"]) if u_info else "-")
    sc2.metric("Status akun", "Aktif" if (u_info and u_info["active"]) else "Nonaktif" if u_info else "-")
    sc3.metric("Login terakhir", recent_login[0][0][:16] if recent_login else "-")
    st.divider()

st.subheader("Log akses")

# limit lebih besar dari default -- halaman ini memang buat telusuri detail,
# bukan sekadar sekilas seperti dulu di Kelola User.
all_matching = []
if selected_actions:
    for act in selected_actions:
        all_matching.extend(db.query_logs(username=username_filter, action=act, since=since, until=until, limit=1000))
    all_matching.sort(key=lambda r: r[0], reverse=True)
else:
    all_matching = db.query_logs(username=username_filter, since=since, until=until, limit=1000)

if all_matching:
    df_logs = pd.DataFrame(all_matching, columns=["Waktu", "Username", "Aksi", "Detail"])
    st.caption(f"{len(df_logs)} baris ditemukan (maks 1000 per aksi).")
    st.dataframe(df_logs, use_container_width=True, hide_index=True, height=450)

    buf = df_logs.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download CSV", data=buf, file_name="audit_trail.csv", mime="text/csv")
else:
    st.info("Tidak ada log yang cocok dengan filter ini.")

st.divider()
st.subheader("Riwayat percobaan login")

attempts = db.get_login_attempts(limit=500)
if attempts:
    df_attempts = pd.DataFrame(attempts, columns=["Waktu", "Username", "Berhasil"])
    if username_filter:
        df_attempts = df_attempts[df_attempts["Username"] == username_filter]
    df_attempts["Berhasil"] = df_attempts["Berhasil"].map({1: "Ya", 0: "GAGAL"})
    only_failed = st.checkbox("Tampilkan yang GAGAL saja", value=False, key="show_failed_only")
    view_attempts = df_attempts[df_attempts["Berhasil"] == "GAGAL"] if only_failed else df_attempts
    st.dataframe(view_attempts, use_container_width=True, hide_index=True)
else:
    st.info("Belum ada riwayat percobaan login.")
