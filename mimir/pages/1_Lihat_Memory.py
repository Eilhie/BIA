"""
1_Lihat_Memory.py (Mimir)
Browse everything Mimir has captured -- both its own memory/ files and
Claude Code's pre-existing memory files for this project. Read-only:
editing/deleting happens by hand in the .md files themselves for now,
same as Claude's own memory system.
"""

from pathlib import Path

import streamlit as st

import indexer
import memory_store

st.set_page_config(page_title="Lihat Memory - Mimir", layout="wide")

st.title("📚 Lihat Memory")
st.caption("Semua yang sudah dicatat Mimir -- lewat `catat:` di chat, upload Excel, atau ditulis langsung ke file.")

TYPE_LABELS = {
    "decision": "🧭 Decision",
    "correction": "🛠️ Correction",
    "process": "⚙️ Process",
    "artifact-structure": "📊 Artifact (struktur)",
    "artifact-purpose": "📊 Artifact (tujuan)",
}

search = st.text_input("🔍 Cari (judul/isi/tag)", "")


def matches(search_term: str, *texts: str) -> bool:
    if not search_term:
        return True
    needle = search_term.lower()
    return any(needle in (t or "").lower() for t in texts)


tab_mimir, tab_claude = st.tabs(["Memory Mimir", "Memory Claude Code"])

with tab_mimir:
    memories = memory_store.list_memories()
    if not memories:
        st.info("Belum ada memory tersimpan. Coba `catat: ...` di halaman Chat, atau upload file Excel.")
    else:
        by_type: dict[str, list[dict]] = {}
        for mem in memories:
            by_type.setdefault(mem["frontmatter"].get("type", "unknown"), []).append(mem)

        st.caption(f"{len(memories)} memory total")
        for mem_type, items in sorted(by_type.items()):
            label = TYPE_LABELS.get(mem_type, mem_type)
            shown = [
                m for m in items
                if matches(search, m["frontmatter"].get("name", ""), m["body"], " ".join(m["frontmatter"].get("tags", [])))
            ]
            if not shown:
                continue
            st.subheader(f"{label} ({len(shown)})")
            for mem in sorted(shown, key=lambda m: m["frontmatter"].get("date", ""), reverse=True):
                fm = mem["frontmatter"]
                title = fm.get("name", mem["path"].stem)
                with st.expander(f"{title} — {fm.get('date', '')}"):
                    if fm.get("tags"):
                        st.caption("Tags: " + ", ".join(fm["tags"]))
                    if fm.get("source_file"):
                        st.caption(f"Sumber file: `{fm['source_file']}`")
                    st.markdown(mem["body"])
                    st.caption(f"📄 `{mem['path'].relative_to(indexer.REPO_ROOT).as_posix()}`")

with tab_claude:
    st.caption(
        "Memory yang sudah ada dari sesi Claude Code sebelumnya (dibaca langsung, "
        "bukan salinan -- lihat mimir/memory/README.md)."
    )
    if not indexer.CLAUDE_MEMORY_DIR.is_dir():
        st.info("Folder memory Claude Code tidak ditemukan di mesin ini.")
    else:
        claude_mems = []
        for path in sorted(indexer.CLAUDE_MEMORY_DIR.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            mem = indexer.read_claude_memory_lenient(path, warn=False)
            if mem is None:
                st.warning(f"Tidak bisa dibaca: {path.name}")
                continue
            claude_mems.append(mem)

        if not claude_mems:
            st.info("Tidak ada memory ditemukan.")
        else:
            st.caption(f"{len(claude_mems)} memory total")
            for mem in claude_mems:
                fm = mem["frontmatter"]
                metadata = fm.get("metadata") or {}
                mem_type = metadata.get("type", "unknown")
                name = fm.get("name", mem["path"].stem)
                desc = fm.get("description", "")
                if not matches(search, name, desc, mem["body"], mem_type):
                    continue
                with st.expander(f"[{mem_type}] {name}"):
                    if desc:
                        st.caption(desc)
                    st.markdown(mem["body"])
                    st.caption(f"📄 `{mem['path'].name}`")
