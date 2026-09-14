"""Streamlit entrypoint: upload documents, then ask questions about them.

Assumptions made while building (none of these are spec requirements):
- Uploaded files are passed to the queue as (filename, bytes) pairs rather
  than via a shared upload directory, so the app and worker containers
  don't need to agree on a path and nothing is written to disk unchunked.
- Collection names are slugified to fit Chroma's naming rules; an empty
  name auto-generates one from a timestamp (FR2 allows either).
- Job status is polled on rerun rather than streamed - simplest thing that
  shows a processing state (FR3).
- Retrieval is plain top-k similarity with k=5 (configurable via TOP_K);
  no reranking or hybrid search.
- Embeddings run locally (FastEmbed); only generation needs an API key, and
  the LLM client is constructed lazily so the UI boots without one.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import config, jobs, rag_chain, vectorstore  # noqa: E402

st.set_page_config(page_title="RAG Generator", page_icon="📚", layout="wide")

DONE_STATES = {"finished", "failed", "stopped", "canceled", "unknown"}


def _pending_jobs() -> list[dict]:
    return st.session_state.setdefault("jobs", [])


def _refresh_jobs() -> None:
    for entry in _pending_jobs():
        if entry["status"] not in DONE_STATES:
            state = jobs.job_state(entry["id"])
            entry.update(status=state["status"], result=state["result"])


# --------------------------------------------------------------------- upload
st.title("📚 RAG Generator")
st.caption(
    "Upload any document set, then ask grounded questions about it. "
    "Switching domains needs a new upload and a new collection name - nothing else."
)

with st.sidebar:
    st.header("Upload documents")
    uploads = st.file_uploader(
        "PDF, DOCX, TXT or MD",
        type=[e.lstrip(".") for e in ("pdf", "docx", "txt", "md")],
        accept_multiple_files=True,
    )
    typed_name = st.text_input(
        "Collection name", placeholder="auto-generated if left blank"
    )
    if st.button("Ingest", type="primary", disabled=not uploads):
        name = typed_name.strip() or f"docs-{datetime.now():%Y%m%d-%H%M%S}"
        payload = [(f.name, f.getvalue()) for f in uploads]
        try:
            job = jobs.enqueue_ingestion(name, payload)
            _pending_jobs().append(
                {
                    "id": job.id,
                    "collection": vectorstore.normalize_collection_name(name),
                    "files": len(payload),
                    "status": "queued",
                    "result": None,
                }
            )
            st.success(f"Queued {len(payload)} file(s) -> `{name}`")
        except Exception as exc:  # redis down, etc.
            st.error(f"Could not enqueue ingestion: {exc}")

    st.divider()
    st.subheader("Ingestion jobs")
    _refresh_jobs()
    if not _pending_jobs():
        st.caption("No jobs this session.")
    for entry in reversed(_pending_jobs()):
        if entry["status"] == "finished":
            chunks = (entry.get("result") or {}).get("chunks", "?")
            st.success(f"`{entry['collection']}` - {chunks} chunks indexed")
        elif entry["status"] == "failed":
            st.error(f"`{entry['collection']}` - ingestion failed")
        else:
            st.info(f"`{entry['collection']}` - {entry['status']}...")
    if any(e["status"] not in DONE_STATES for e in _pending_jobs()):
        if st.button("Refresh status"):
            st.rerun()

# ---------------------------------------------------------------------- query
try:
    collections = vectorstore.list_collections()
except Exception as exc:
    collections = []
    st.error(f"Vector store unavailable: {exc}")

if not collections:
    st.info("Upload a document set to get started.")
    st.stop()

collection = st.selectbox("Collection", collections)
st.caption(
    f"{vectorstore.collection_size(collection)} chunks indexed - "
    f"answers are generated only from this collection."
)

question = st.chat_input("Ask a question about this collection")
history = st.session_state.setdefault("history", {})
turns = history.setdefault(collection, [])

if question:
    with st.spinner("Retrieving and answering..."):
        try:
            result = rag_chain.answer_question(
                collection, question, k=config.TOP_K
            )
        except Exception as exc:
            result = {"answer": f"Generation failed: {exc}", "sources": []}
    turns.append({"question": question, **result})

for turn in turns:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        if turn.get("sources"):
            with st.expander(f"Sources ({len(turn['sources'])} chunks)"):
                for source in turn["sources"]:
                    st.markdown(
                        f"**{source['source']}** - chunk {source['chunk_index']}"
                    )
                    st.caption(source["text"][:400])
