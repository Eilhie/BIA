"""
app.py (Mimir)
Chat UI for Mimir, the local Wiki LLM -- retrieval-augmented Q&A over
heimdall's README + module docstrings, running entirely through a local
Ollama instance (localhost:11434 only, nothing leaves this machine).

Named after the Norse keeper of wisdom, whose counsel could always be
sought -- the point of this app: institutional "why" knowledge that stays
answerable, not buried in scattered code comments and one person's memory.

Deliberately calls the index + Ollama directly in-process rather than
through a separate API service -- this is a single-user local tool, so a
second HTTP hop would only add moving parts without solving a real problem.

Run via mimir/run.bat, or manually:
    venv/Scripts/python.exe -m streamlit run app.py --server.port 8600
"""

import io
import json
import time

import chromadb
import ollama
import openpyxl
import streamlit as st

import bench
import indexer
import memory_store

st.set_page_config(page_title="Mimir - SDA", layout="wide")

MODELS = ["hermes3:8b", "qwen2.5:7b-instruct"]
TOP_K = 4
CATAT_PREFIX = "catat:"
MAX_HISTORY_MESSAGES = 20  # ~10 exchanges -- plenty of headroom left in either
                           # model's context window, just bounded so a very
                           # long session doesn't keep growing the prompt forever

SYSTEM_PROMPT = """Nama Anda adalah Mimir -- asisten wiki internal (Wiki LLM) milik \
PT SDA yang berjalan sepenuhnya lokal di komputer ini. Anda BUKAN Heimdall -- \
Heimdall adalah nama aplikasi web TERPISAH (folder heimdall/) yang mengolah data \
OMSHAR/EAO, dan tugas Anda adalah menjawab pertanyaan TENTANG Heimdall berdasarkan \
dokumentasinya, bukan menjadi Heimdall itu sendiri. Kalau ditanya siapa Anda, \
jawab: Anda adalah Mimir.

Jawab HANYA berdasarkan potongan dokumentasi yang diberikan di bawah -- jangan \
mengarang informasi yang tidak ada di situ. Konteks yang diberikan bisa berasal dari \
README/docstring kode Heimdall, ATAU dari memory yang sudah dicatat sebelumnya \
(keputusan, koreksi, proses, atau struktur file Excel) -- keduanya sama validnya \
sebagai sumber jawaban.

PENTING: Anda belum bisa mengambil angka penjualan/omset/klaim SKU yang sebenarnya \
(fitur pencarian data real belum tersambung ke chat ini). Kalau user menanyakan \
angka spesifik (omset outlet tertentu, QTY klaim SKU, dsb), JANGAN mengarang \
angka -- katakan dengan jelas bahwa Anda hanya bisa menjawab pertanyaan tentang \
cara kerja sistem, dan arahkan user ke halaman aslinya di app utama (Omset Seeker, \
Cek Klaim SKU, dst) untuk angka real.

Jawab dalam Bahasa Indonesia, singkat dan jelas."""

MEMORY_DRAFT_PROMPT = """Anda membantu menyusun catatan memory dari pesan user. \
Baca pesan user di bawah dan hasilkan draft memory dalam format JSON persis sesuai \
schema yang diberikan. Field "type" HARUS salah satu dari: "decision", "correction", \
"process". Field "title" singkat (maks 8 kata). Field "tags" 1-4 kata kunci relevan. \
Field "content" adalah isi memory yang rapi (boleh sedikit dirapikan dari pesan asli, \
tapi JANGAN menambahkan informasi yang tidak disebutkan user)."""

MEMORY_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["decision", "correction", "process"]},
        "title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "content": {"type": "string"},
    },
    "required": ["type", "title", "tags", "content"],
}


@st.cache_resource
def get_chroma_collection():
    client = chromadb.PersistentClient(path=str(indexer.INDEX_DIR))
    return client.get_collection(indexer.COLLECTION_NAME)


def retrieve_context(query: str, top_k: int = TOP_K) -> list[dict]:
    collection = get_chroma_collection()
    query_embedding = ollama.embed(model=indexer.EMBED_MODEL, input=query)["embeddings"][0]
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    return [
        {"text": doc, "source": meta["source"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def build_prompt(query: str, chunks: list[dict]) -> str:
    context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    return f"Konteks dokumentasi:\n\n{context}\n\nPertanyaan: {query}"


def build_history(exclude_last: bool = True) -> list[dict]:
    """Prior turns as plain {role, content} dicts for ollama.chat(), capped
    to MAX_HISTORY_MESSAGES. Without this, every question was previously
    sent as an isolated conversation with no memory of anything said
    before it in the same session -- the chat log LOOKED continuous
    (Streamlit just replays session_state.messages on screen) but the
    model itself never saw any of it, so a follow-up like "kenapa kamu
    bilang begitu" (why did you say that) had literally nothing to refer
    back to and just repeated a generic answer.

    exclude_last=True drops the just-appended current question, since
    that gets sent separately (with fresh retrieved context attached),
    not replayed as bare history."""
    msgs = st.session_state.messages[:-1] if exclude_last else st.session_state.messages
    history = [{"role": m["role"], "content": m["content"]} for m in msgs]
    return history[-MAX_HISTORY_MESSAGES:]


def draft_memory(model: str, raw_text: str) -> tuple[dict, dict]:
    """Sends the user's `catat:` message to the LLM asking for structured
    JSON output (type/title/tags/content) -- a fixed schema is far more
    reliable than parsing free text out of an 8B model's response.

    Returns (draft, timing) -- timing logged via bench.log() same as the
    main chat flow, so `catat:` drafts count toward the model benchmark too
    (kind="catat_draft", separate from "chat" so sidebar averages aren't
    skewed by a different kind of call)."""
    t0 = time.perf_counter()
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": MEMORY_DRAFT_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        format=MEMORY_DRAFT_SCHEMA,
    )
    elapsed = time.perf_counter() - t0
    timing = bench.log(
        "catat_draft", model, retrieval_s=0.0, generate_s=elapsed, total_s=elapsed,
        ollama_stats=resp if isinstance(resp, dict) else None,
    )
    return json.loads(resp["message"]["content"]), timing


def extract_excel_structure(file_bytes: bytes, filename: str) -> str:
    """Sheet names + header row per sheet -- structure only, never actual
    data rows, so nothing here can leak real figures into the index."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=False)
    lines = [f"File: {filename}", f"Sheets: {', '.join(wb.sheetnames)}", ""]
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        try:
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        except StopIteration:
            header_row = ()
        headers = [str(h) for h in header_row if h is not None]
        lines.append(f"## Sheet: {sheet_name}")
        lines.append(f"Columns: {', '.join(headers) if headers else '(kosong/tidak terbaca)'}")
        lines.append("")
    wb.close()
    return "\n".join(lines)


# ── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Mimir")
    st.caption("Lokal & offline -- tidak ada data yang keluar dari mesin ini.")

    model = st.selectbox("Model", MODELS, index=0)

    try:
        chunk_count = get_chroma_collection().count()
        st.caption(f"Index: {chunk_count} chunks")
    except Exception:
        st.warning("Index belum ada -- klik 'Bangun ulang index' di bawah.")

    if st.button("🔄 Bangun ulang index"):
        with st.spinner("Mengindeks ulang README + docstrings..."):
            get_chroma_collection.clear()
            n = indexer.build_index()
        st.success(f"Selesai -- {n} chunks terindeks.")
        st.rerun()

    if st.button("🗑️ Hapus riwayat chat"):
        st.session_state.messages = []
        st.rerun()

    with st.expander("📊 Benchmark model"):
        summary = bench.summarize_by_model()
        if not summary:
            st.caption("Belum ada respons chat yang tercatat.")
        else:
            for row in summary:
                tok = f", {row['avg_tokens_per_sec']} tok/s" if row["avg_tokens_per_sec"] else ""
                st.caption(f"**{row['model']}** -- {row['avg_total_s']}s rata-rata ({row['n']}x{tok})")

    st.divider()
    with st.expander("📊 Tambah Artifact Excel"):
        st.caption("Struktur (sheet/kolom) diambil otomatis. Tujuan file HARUS Anda tulis sendiri -- tidak pernah ditebak.")
        uploaded = st.file_uploader("File Excel", type=["xlsx"], key="excel_uploader")
        purpose = st.text_area("Tujuan file ini (opsional, tapi disarankan)", key="excel_purpose")
        if st.button("Simpan Artifact", disabled=uploaded is None):
            structure_text = extract_excel_structure(uploaded.getvalue(), uploaded.name)
            struct_path = memory_store.save_memory(
                "artifact-structure", uploaded.name, structure_text, source_file=uploaded.name,
            )
            indexer.add_single_chunk(structure_text, str(struct_path.relative_to(indexer.REPO_ROOT).as_posix()), "memory", "artifact-structure")
            saved_msg = f"Struktur tersimpan: `{struct_path.name}`"

            if purpose.strip():
                purpose_path = memory_store.save_memory(
                    "artifact-purpose", uploaded.name, purpose.strip(), source_file=uploaded.name,
                )
                indexer.add_single_chunk(purpose.strip(), str(purpose_path.relative_to(indexer.REPO_ROOT).as_posix()), "memory", "artifact-purpose")
                saved_msg += f" + tujuan tersimpan: `{purpose_path.name}`"
            else:
                saved_msg += " (tujuan belum diisi -- tidak dicatat, bisa ditambahkan lagi nanti dengan upload ulang)"

            get_chroma_collection.clear()
            st.success(saved_msg)

# ── Chat state ───────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_memory" not in st.session_state:
    st.session_state.pending_memory = None
if "pending_memory_timing" not in st.session_state:
    st.session_state.pending_memory_timing = None

st.title("Mimir -- SDA Internal Wiki")
st.caption(
    "Tanya apa saja tentang cara kerja pipeline OMSHAR/EAO. Jawaban diambil dari "
    "README, komentar kode, dan memory yang sudah dicatat -- bukan dikarang. "
    f"Ketik `{CATAT_PREFIX} ...` untuk mencatat keputusan/koreksi/proses baru."
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("timing"):
            st.caption(bench.format_caption(msg["timing"]))
        if msg.get("sources"):
            with st.expander("Sumber"):
                for s in msg["sources"]:
                    st.caption(f"📄 {s}")

# ── Pending memory confirmation (survives reruns until Simpan/Batal) ─────
if st.session_state.pending_memory:
    draft = st.session_state.pending_memory
    with st.chat_message("assistant"):
        st.markdown(f"**Draft memory -- {draft['type']}**")
        st.markdown(f"**{draft['title']}**")
        st.caption("Tags: " + ", ".join(draft["tags"]))
        st.markdown(draft["content"])
        if st.session_state.pending_memory_timing:
            st.caption(bench.format_caption(st.session_state.pending_memory_timing))
        col1, col2 = st.columns(2)
        if col1.button("✅ Simpan", key="save_memory"):
            path = memory_store.save_memory(draft["type"], draft["title"], draft["content"], tags=draft["tags"])
            rel = path.relative_to(indexer.REPO_ROOT).as_posix()
            indexer.add_single_chunk(draft["content"], rel, "memory", draft["type"])
            get_chroma_collection.clear()
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"✅ Tersimpan sebagai `{path.name}` dan langsung bisa dicari.",
            })
            st.session_state.pending_memory = None
            st.session_state.pending_memory_timing = None
            st.rerun()
        if col2.button("❌ Batal", key="cancel_memory"):
            st.session_state.messages.append({"role": "assistant", "content": "❌ Dibatalkan, tidak disimpan."})
            st.session_state.pending_memory = None
            st.session_state.pending_memory_timing = None
            st.rerun()

# ── Handle new question ──────────────────────────────────────────────────
if question := st.chat_input("Tanya sesuatu, atau `catat: ...` untuk mencatat memory baru..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if question.strip().lower().startswith(CATAT_PREFIX):
        raw_text = question.strip()[len(CATAT_PREFIX):].strip()
        with st.chat_message("assistant"):
            with st.spinner("Menyusun draft memory..."):
                try:
                    draft, draft_timing = draft_memory(model, raw_text)
                    st.session_state.pending_memory = draft
                    st.session_state.pending_memory_timing = draft_timing
                except (json.JSONDecodeError, KeyError) as e:
                    st.error(f"Gagal menyusun draft -- coba tulis ulang lebih jelas. ({e})")
                except Exception as e:
                    st.error(
                        f"Gagal menghubungi Ollama ({type(e).__name__}: {e}) -- "
                        "pastikan Ollama sudah jalan (`ollama serve`) dan model-nya sudah di-pull."
                    )
        st.rerun()
    else:
        with st.chat_message("assistant"):
            t0 = time.perf_counter()
            with st.spinner("Mencari dokumentasi relevan..."):
                try:
                    chunks = retrieve_context(question)
                except Exception as e:
                    st.error(
                        f"Gagal menghubungi Ollama/index ({type(e).__name__}: {e}) -- "
                        "pastikan Ollama sudah jalan (`ollama serve`) dan index sudah dibangun."
                    )
                    st.stop()
            t_retrieved = time.perf_counter()
            sources = sorted({c["source"] for c in chunks})

            prompt = build_prompt(question, chunks)
            try:
                stream = ollama.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *build_history(),
                        {"role": "user", "content": prompt},
                    ],
                    stream=True,
                )
            except Exception as e:
                st.error(
                    f"Gagal menghubungi Ollama ({type(e).__name__}: {e}) -- "
                    "pastikan Ollama sudah jalan (`ollama serve`) dan model-nya sudah di-pull."
                )
                st.stop()

            # Simpan chunk TERAKHIR (done=True) -- itu yang bawa statistik asli
            # dari Ollama sendiri (eval_count/eval_duration, dst), dipakai
            # bench.log() untuk hitung tokens/sec yang akurat (bukan cuma
            # wall-clock Python yang ikut kehitung overhead Streamlit).
            final_part = {}

            def token_stream():
                for part in stream:
                    if part.get("done"):
                        final_part.update(part)
                    content = part.get("message", {}).get("content", "")
                    if content:
                        yield content

            answer = st.write_stream(token_stream())
            t_end = time.perf_counter()

            timing = bench.log(
                "chat", model,
                retrieval_s=t_retrieved - t0,
                generate_s=t_end - t_retrieved,
                total_s=t_end - t0,
                ollama_stats=final_part or None,
            )
            st.caption(bench.format_caption(timing))

            with st.expander("Sumber"):
                for s in sources:
                    st.caption(f"📄 {s}")

        st.session_state.messages.append({
            "role": "assistant", "content": answer, "sources": sources, "timing": timing,
        })
