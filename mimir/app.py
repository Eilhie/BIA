"""
app.py (Mimir)
Chat UI for Mimir, the local Wiki LLM -- retrieval-augmented Q&A over
omset-app's README + module docstrings, running entirely through a local
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

import chromadb
import ollama
import streamlit as st

import indexer

st.set_page_config(page_title="Mimir - SDA", layout="wide")

MODELS = ["hermes3:8b", "qwen2.5:7b-instruct"]
TOP_K = 4

SYSTEM_PROMPT = """Anda adalah asisten dokumentasi internal untuk sistem pelaporan \
penjualan OMSHAR/EAO milik PT SDA (folder omset-app/). Jawab HANYA berdasarkan \
potongan dokumentasi yang diberikan di bawah -- jangan mengarang informasi yang \
tidak ada di situ.

PENTING: Anda belum bisa mengambil angka penjualan/omset/klaim SKU yang sebenarnya \
(fitur pencarian data real belum tersambung ke chat ini). Kalau user menanyakan \
angka spesifik (omset outlet tertentu, QTY klaim SKU, dsb), JANGAN mengarang \
angka -- katakan dengan jelas bahwa Anda hanya bisa menjawab pertanyaan tentang \
cara kerja sistem, dan arahkan user ke halaman aslinya di app utama (Omset Seeker, \
Cek Klaim SKU, dst) untuk angka real.

Jawab dalam Bahasa Indonesia, singkat dan jelas."""


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

# ── Chat state ───────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("Mimir -- SDA Internal Wiki")
st.caption("Tanya apa saja tentang cara kerja pipeline OMSHAR/EAO. Jawaban diambil dari README + komentar kode, bukan dikarang.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("Sumber"):
                for s in msg["sources"]:
                    st.caption(f"📄 {s}")

# ── Handle new question ──────────────────────────────────────────────────
if question := st.chat_input("Tanya sesuatu tentang sistem OMSHAR/EAO..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Mencari dokumentasi relevan..."):
            chunks = retrieve_context(question)
        sources = sorted({c["source"] for c in chunks})

        prompt = build_prompt(question, chunks)
        stream = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )

        def token_stream():
            for part in stream:
                yield part["message"]["content"]

        answer = st.write_stream(token_stream())

        with st.expander("Sumber"):
            for s in sources:
                st.caption(f"📄 {s}")

    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})
