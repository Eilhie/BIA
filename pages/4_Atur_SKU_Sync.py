"""
ATUR SKU SYNC
Kelola SKU_LIST (D:\\DB OMSHAR\\SKU_LIST\\{UMUM,HOREKA}\\*.txt) -- daftar kode SKU yang
ditarik (robocopy) dari server pas Sync (lihat _sync_worker() di halaman Sync & Transpose).
Tiap file .txt = satu grup, isinya kode SKU satu per baris. Kode ditandai "dipakai
pipeline" kalau ada di UMUM_FILE/HOREKA_FILE/HOREKA_KEG_FILE (transpose.py) -- itu yang
dipakai laporan, hapus kode itu berarti Sync berhenti menariknya dan laporan brand terkait
bisa jadi basi/kosong.
"""

import os
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(r"D:\SDAAREA\omset_pipeline")))
import transpose as t  # noqa: E402

st.set_page_config(page_title="Atur SKU Sync", layout="wide")
st.title("Atur SKU Sync")
st.caption(
    "Kelola daftar SKU yang ditarik dari server pas Sync. Tiap grup di bawah = 1 file "
    "`.txt` di `SKU_LIST`. Kode yang ditandai **dipakai pipeline** dipakai laporan -- "
    "hati-hati kalau mau dihapus, Sync akan berhenti menariknya. Lihat halaman "
    "**SKU Manifest** untuk audit lengkap coverage-nya."
)

SKU_LIST_DIR = Path(r"D:\DB OMSHAR\SKU_LIST")


def _used_codes(category: str) -> set[str]:
    file_map = t.UMUM_FILE if category == "UMUM" else t.HOREKA_FILE
    used = {code for files in file_map.values() for code in files}
    if category == "HOREKA":
        used |= {code for files in t.HOREKA_KEG_FILE.values() for code in files}
    return used


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8-sig")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_lines(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]


def _save_lines(path: Path, lines: list[str]) -> None:
    _atomic_write_text(path, ("\n".join(lines) + "\n") if lines else "")


category = st.radio("Kategori", ["UMUM", "HOREKA"], horizontal=True, key="manage_cat")
cat_dir = SKU_LIST_DIR / category
cat_dir.mkdir(parents=True, exist_ok=True)
used = _used_codes(category)

st.divider()

with st.expander("+ Tambah grup baru"):
    new_name = st.text_input("Nama grup (jadi nama file .txt)", key="new_group_name")
    new_codes = st.text_area("Kode SKU (satu per baris)", key="new_group_codes", height=100)
    if st.button("Buat grup", key="new_group_create"):
        name = new_name.strip()
        target = cat_dir / f"{name}.txt"
        if not name:
            st.error("Nama grup tidak boleh kosong.")
        elif target.exists():
            st.error(f"Grup '{name}' sudah ada.")
        else:
            codes = [c.strip() for c in new_codes.splitlines() if c.strip()]
            _save_lines(target, codes)
            st.success(f"Grup '{name}' dibuat dengan {len(codes)} kode.")
            st.rerun()

st.divider()

txt_files = sorted(cat_dir.glob("*.txt"))
if not txt_files:
    st.info(f"Belum ada grup SKU untuk {category}.")

for txt_path in txt_files:
    group = txt_path.stem
    lines = _read_lines(txt_path)
    used_here = [c for c in lines if c in used]
    label = f"{group}  --  {len(lines)} kode, {len(used_here)} dipakai pipeline"

    with st.expander(label):
        if used_here:
            st.caption("Dipakai pipeline: " + ", ".join(f"`{c}`" for c in used_here))

        text_val = st.text_area(
            "Kode SKU (satu per baris)",
            value="\n".join(lines),
            height=220,
            key=f"edit_{category}_{group}",
        )

        col_save, col_del = st.columns([1, 1])
        save_clicked = col_save.button("Simpan perubahan", key=f"save_{category}_{group}")
        del_clicked = col_del.button("Hapus grup ini", key=f"delrequest_{category}_{group}")

        if save_clicked:
            new_lines = [l.strip() for l in text_val.splitlines() if l.strip()]
            removed_used = (set(lines) & used) - set(new_lines)
            if removed_used:
                st.session_state[f"confirm_remove_{category}_{group}"] = (new_lines, removed_used)
            else:
                _save_lines(txt_path, new_lines)
                st.success("Tersimpan.")
                st.rerun()

        confirm_remove_key = f"confirm_remove_{category}_{group}"
        if confirm_remove_key in st.session_state:
            pending_lines, removed_used = st.session_state[confirm_remove_key]
            st.warning(
                "Kode ini dipakai pipeline dan akan berhenti disync: "
                + ", ".join(f"`{c}`" for c in sorted(removed_used))
            )
            c1, c2 = st.columns(2)
            if c1.button("Tetap simpan", key=f"confirmyes_{category}_{group}"):
                _save_lines(txt_path, pending_lines)
                del st.session_state[confirm_remove_key]
                st.success("Tersimpan.")
                st.rerun()
            if c2.button("Batal", key=f"confirmno_{category}_{group}"):
                del st.session_state[confirm_remove_key]
                st.rerun()

        if del_clicked:
            st.session_state[f"confirm_delete_{category}_{group}"] = True

        confirm_delete_key = f"confirm_delete_{category}_{group}"
        if st.session_state.get(confirm_delete_key):
            st.error(f"Yakin hapus grup '{group}' seluruhnya? Semua {len(lines)} kode di dalamnya berhenti disync.")
            c1, c2 = st.columns(2)
            if c1.button("Ya, hapus grup", key=f"delyes_{category}_{group}"):
                txt_path.unlink()
                del st.session_state[confirm_delete_key]
                st.success(f"Grup '{group}' dihapus.")
                st.rerun()
            if c2.button("Batal", key=f"delno_{category}_{group}"):
                del st.session_state[confirm_delete_key]
                st.rerun()
