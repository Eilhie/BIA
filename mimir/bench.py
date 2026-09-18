"""
bench.py (Mimir)
Per-response LLM timing, appended to a local JSONL log -- this is what the
README's "no default has been picked yet" side-by-side comparison between
hermes3:8b and qwen2.5:7b-instruct is actually based on. Local-only,
gitignored, never leaves this machine (same as everything else Mimir touches).

Two timing sources are recorded, on purpose:
  - Wall-clock (retrieval_s / generate_s / total_s), measured here -- includes
    Streamlit/Python overhead, so it's what the user actually experiences.
  - Ollama's own reported stats (eval_count/eval_duration, etc, from the final
    streamed chunk when stream=True) -- excludes that overhead, so it's what
    the model itself is actually doing, and lets tokens/sec be computed
    precisely. Not always present (older Ollama versions, or a non-streaming
    call) -- callers should treat every ollama_stats field as optional.
"""

import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / ".bench.jsonl"


def log(kind: str, model: str, retrieval_s: float, generate_s: float,
        total_s: float, ollama_stats: dict | None = None) -> dict:
    """Appends one benchmark entry, returns it (so the caller can also show
    it in the UI without re-reading the file)."""
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,  # "chat" (normal Q&A) or "catat_draft" (memory drafting)
        "model": model,
        "retrieval_s": round(retrieval_s, 3),
        "generate_s": round(generate_s, 3),
        "total_s": round(total_s, 3),
    }
    if ollama_stats:
        eval_count = ollama_stats.get("eval_count")
        eval_duration = ollama_stats.get("eval_duration")
        if eval_count and eval_duration:
            entry["eval_count"] = eval_count
            entry["tokens_per_sec"] = round(eval_count / (eval_duration / 1e9), 2)
        prompt_eval_duration = ollama_stats.get("prompt_eval_duration")
        if prompt_eval_duration is not None:
            entry["prompt_eval_s"] = round(prompt_eval_duration / 1e9, 3)
        total_duration = ollama_stats.get("total_duration")
        if total_duration is not None:
            entry["ollama_total_s"] = round(total_duration / 1e9, 3)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def format_caption(entry: dict) -> str:
    parts = [
        f"⏱️ {entry['total_s']:.2f}s total "
        f"(retrieval {entry['retrieval_s']:.2f}s + generate {entry['generate_s']:.2f}s)"
    ]
    if entry.get("tokens_per_sec"):
        parts.append(f"{entry['tokens_per_sec']:.1f} tok/s")
    return " · ".join(parts)


def read_all() -> list[dict]:
    """Every logged entry, oldest first -- corrupt/partial last lines
    (mis. app dimatikan paksa di tengah write) di-skip, bukan crash
    seluruh pembacaan."""
    if not LOG_PATH.exists():
        return []
    entries = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize_by_model(kind: str = "chat") -> list[dict]:
    """Rata-rata total_s dan tokens/sec per model, cuma dari entry kind
    tertentu (default "chat" -- QnA biasa, bukan draft catat:) -- ini yang
    ditampilkan di sidebar buat perbandingan model side-by-side."""
    entries = [e for e in read_all() if e.get("kind") == kind]
    by_model: dict[str, list[dict]] = {}
    for e in entries:
        by_model.setdefault(e["model"], []).append(e)

    summary = []
    for model, rows in by_model.items():
        n = len(rows)
        avg_total = sum(r["total_s"] for r in rows) / n
        tok_rows = [r["tokens_per_sec"] for r in rows if r.get("tokens_per_sec")]
        summary.append({
            "model": model,
            "n": n,
            "avg_total_s": round(avg_total, 2),
            "avg_tokens_per_sec": round(sum(tok_rows) / len(tok_rows), 1) if tok_rows else None,
        })
    return sorted(summary, key=lambda s: s["model"])
