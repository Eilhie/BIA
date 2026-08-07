"""
KELOLA USER
Halaman khusus level 5 (Admin) -- buat/ubah akun, atur level akses (0-5),
nonaktifkan akun, reset password, dan lihat audit trail (siapa buka halaman
apa, riwayat percobaan login sukses/gagal) untuk keperluan pengawasan akses.
"""

import pandas as pd
import streamlit as st

import auth
import database as db

st.set_page_config(page_title="Kelola User", layout="wide")
current = auth.require_level(5, page="Kelola User")
st.title("Kelola User")
st.caption(
    "Kelola akun dan level akses (0-5) untuk semua tools OMSHAR/MClub. "
    "Lihat config/config.yaml untuk daftar level minimum tiap halaman."
)

with st.expander("Keterangan level", expanded=False):
    for lvl, label in sorted(auth.LEVEL_LABELS.items()):
        st.caption(f"**{lvl}** -- {label}")

st.divider()
st.subheader("0. Permintaan akun baru (pending)")
st.caption(
    "Diajukan sendiri oleh calon user lewat form 'Belum punya akun? Request di sini' "
    "di halaman Login -- password sudah dipilih & di-hash sendiri oleh mereka, Admin "
    "tinggal tentukan level akses lalu Setujui (atau Tolak kalau tidak dikenal/salah)."
)

pending = db.list_pending_requests()
if not pending:
    st.caption("Tidak ada permintaan yang menunggu.")
else:
    for req in pending:
        with st.container(border=True):
            rc1, rc2, rc3, rc4 = st.columns([2, 2, 1, 1])
            rc1.markdown(f"**{req['username']}**")
            rc1.caption(req["created_at"])
            rc2.caption(req["note"] or "(tidak ada catatan)")
            req_level = rc3.selectbox(
                "Level", options=sorted(auth.LEVEL_LABELS.keys()), index=1,
                format_func=lambda l: f"{l} - {auth.LEVEL_LABELS[l]}", key=f"req_level_{req['id']}",
                label_visibility="collapsed",
            )
            if rc4.button("Setujui", key=f"approve_{req['id']}", type="primary"):
                if db.get_user(req["username"]) is not None:
                    st.error(f"Username '{req['username']}' sudah dipakai user lain -- tolak request ini.")
                else:
                    db.approve_account_request(req["id"], req_level)
                    db.log_action(current["username"], "setujui_request_akun",
                                   f"{req['username']} -> level {req_level}")
                    st.success(f"Akun '{req['username']}' dibuat dengan level {req_level}.")
                    st.rerun()
            if rc4.button("Tolak", key=f"reject_{req['id']}"):
                db.reject_account_request(req["id"])
                db.log_action(current["username"], "tolak_request_akun", req["username"])
                st.rerun()

st.divider()
st.subheader("1. Tambah user baru")

with st.form("add_user_form", clear_on_submit=True):
    c1, c2, c3 = st.columns([2, 2, 1])
    new_username = c1.text_input("Username")
    new_password = c2.text_input("Password", type="password")
    new_level = c3.selectbox("Level", options=sorted(auth.LEVEL_LABELS.keys()), index=1,
                              format_func=lambda l: f"{l} - {auth.LEVEL_LABELS[l]}")
    add_submitted = st.form_submit_button("Tambah User", type="primary")

if add_submitted:
    uname = new_username.strip()
    if not uname or not new_password:
        st.error("Username dan password wajib diisi.")
    elif len(new_password) < 6:
        st.error("Password minimal 6 karakter.")
    elif db.get_user(uname) is not None:
        st.error(f"Username '{uname}' sudah ada.")
    else:
        db.create_user(uname, auth._hash_password(new_password), new_level)
        db.log_action(current["username"], "tambah_user", f"{uname} -> level {new_level}")
        st.success(f"User '{uname}' dibuat dengan level {new_level} ({auth.level_label(new_level)}).")
        st.rerun()

st.divider()
st.subheader("2. Daftar user")

users = db.list_users()
if not users:
    st.info("Belum ada user.")
else:
    active_level5 = [u["username"] for u in users if u["level"] == 5 and u["active"]]
    for u in users:
        with st.expander(
            f"{u['username']} -- level {u['level']} ({auth.level_label(u['level'])})"
            + ("" if u["active"] else "  [NONAKTIF]"),
            expanded=False,
        ):
            ec1, ec2, ec3 = st.columns([2, 2, 2])
            edit_level = ec1.selectbox(
                "Level", options=sorted(auth.LEVEL_LABELS.keys()), index=u["level"],
                format_func=lambda l: f"{l} - {auth.LEVEL_LABELS[l]}", key=f"level_{u['username']}",
            )
            edit_active = ec2.checkbox("Aktif", value=u["active"], key=f"active_{u['username']}")
            new_pw = ec3.text_input("Reset password (kosongkan kalau tidak diubah)",
                                     type="password", key=f"pw_{u['username']}")

            if st.button("Simpan", key=f"save_{u['username']}"):
                would_remove_last_admin = (
                    u["username"] in active_level5
                    and len(active_level5) <= 1
                    and (edit_level != 5 or not edit_active)
                )
                if would_remove_last_admin:
                    st.error(
                        "Tidak bisa: ini satu-satunya akun Admin (level 5) aktif yang tersisa. "
                        "Buat/aktifkan Admin lain dulu sebelum menurunkan/nonaktifkan akun ini."
                    )
                else:
                    changes = []
                    if edit_level != u["level"]:
                        db.set_user_level(u["username"], edit_level)
                        changes.append(f"level {u['level']}->{edit_level}")
                    if edit_active != u["active"]:
                        db.set_user_active(u["username"], edit_active)
                        changes.append(f"aktif {u['active']}->{edit_active}")
                    if new_pw:
                        if len(new_pw) < 6:
                            st.error("Password baru minimal 6 karakter -- perubahan lain tetap disimpan.")
                        else:
                            db.set_user_password(u["username"], auth._hash_password(new_pw))
                            changes.append("password direset")
                    if changes:
                        db.log_action(current["username"], "ubah_user", f"{u['username']}: {', '.join(changes)}")
                        st.success(f"Perubahan disimpan: {', '.join(changes)}.")
                        st.rerun()
                    else:
                        st.info("Tidak ada perubahan.")

    df_users = pd.DataFrame(users)
    st.caption(f"{len(df_users)} user terdaftar.")
    st.dataframe(df_users, use_container_width=True, hide_index=True)

st.divider()
st.subheader("3. Audit trail -- akses halaman")

logs = db.get_logs(limit=300)
if logs:
    df_logs = pd.DataFrame(logs, columns=["Waktu", "Username", "Aksi", "Detail"])
    filter_user = st.text_input("Filter username (kosongkan untuk semua)", key="log_filter_user")
    view_logs = df_logs
    if filter_user.strip():
        view_logs = view_logs[view_logs["Username"].str.contains(filter_user.strip(), case=False, na=False)]
    st.dataframe(view_logs, use_container_width=True, hide_index=True)
else:
    st.info("Belum ada log akses.")

st.divider()
st.subheader("4. Riwayat percobaan login")

attempts = db.get_login_attempts(limit=300)
if attempts:
    df_attempts = pd.DataFrame(attempts, columns=["Waktu", "Username", "Berhasil"])
    df_attempts["Berhasil"] = df_attempts["Berhasil"].map({1: "Ya", 0: "GAGAL"})
    only_failed = st.checkbox("Tampilkan yang GAGAL saja", value=False, key="show_failed_only")
    view_attempts = df_attempts[df_attempts["Berhasil"] == "GAGAL"] if only_failed else df_attempts
    st.dataframe(view_attempts, use_container_width=True, hide_index=True)
else:
    st.info("Belum ada riwayat percobaan login.")
