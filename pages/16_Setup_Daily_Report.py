"""
SETUP DAILY REPORT
Halaman -- logika sebenarnya ada di daily_report_setup.py (dipakai bareng
dengan modal notifikasi di app.py, lihat itu untuk penjelasan lengkap).
Auto-jalan begitu halaman ini dibuka, sama seperti pola BPR
(backup_excel_to_local() di pages/13_BPR.py) -- idempotent, tidak pernah
menimpa/menghapus file yang sudah tersalin.
"""

import streamlit as st

import auth
import daily_report_setup as drs

auth.require_level(5, page="Setup Daily Report")
st.title("Setup Daily Report")

target = drs.today_target_folder()
files = drs.root_files()

st.caption(f"Sumber: `{drs.ROOT_DIR}` ({len(files)} file langsung di root, bukan subfolder) &rarr; Tujuan hari ini: `{target}`")

already_existed = target.exists()
result = drs.run_setup()

if result["copied"]:
    st.success(f"{len(result['copied'])} file baru disalin ke folder hari ini.")
if result["skipped"] and not result["copied"]:
    st.success(f"Folder hari ini sudah lengkap ({len(result['skipped'])}/{len(files)} file) -- tidak ada yang perlu dilakukan.")
elif result["skipped"]:
    st.caption(f"{len(result['skipped'])} file lain sudah ada dari sebelumnya, tidak ditimpa ulang.")
if result["failed"]:
    st.error(f"{len(result['failed'])} file GAGAL disalin:")
    for name, err in result["failed"]:
        st.write(f"- {name}: {err}")

with st.expander(f"Detail ({len(files)} file di root)"):
    for f in sorted(files, key=lambda p: p.name):
        if f.name in result["copied"]:
            status = "baru disalin"
        elif f.name in result["skipped"]:
            status = "sudah ada"
        else:
            status = "GAGAL"
        st.write(f"- {f.name} -- {status}")

st.divider()
st.caption(
    f"Folder tujuan {'sudah ada sebelumnya' if already_existed else 'baru dibuat hari ini'}. "
    "Aman dibuka berkali-kali sehari -- file yang sudah tersalin tidak akan ditimpa ulang."
)
