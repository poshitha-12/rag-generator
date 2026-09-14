"""ChromaDB collection management.

Each uploaded document set lives in its own named, persistent collection
(FR2), so switching domains is an upload plus a name — never a code
change (FR7).
"""

from __future__ import annotations

import re

import chromadb
from langchain_community.vectorstores import Chroma

from app import config

_embeddings = None
_reranker = None


def get_embeddings():
    """Local (ONNX, no API key) embeddings, loaded once per process."""
    global _embeddings
    if _embeddings is None:
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

        options = {"model_name": config.EMBEDDING_MODEL} if config.EMBEDDING_MODEL else {}
        _embeddings = FastEmbedEmbeddings(**options)
    return _embeddings


def get_reranker():
    """Local (ONNX, no API key) cross-encoder, loaded once per process."""
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _reranker = TextCrossEncoder(model_name=config.RERANK_MODEL)
    return _reranker


def normalize_collection_name(name: str) -> str:
    """Coerce a user-supplied name into something Chroma accepts."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug) or "collection"
    if not slug[0].isalnum():
        slug = "c" + slug
    slug = slug[:63]
    while len(slug) < 3:
        slug += "0"
    if not slug[-1].isalnum():
        slug = slug[:-1] + "0"
    return slug


def _client(persist_dir: str | None = None) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=persist_dir or config.CHROMA_PERSIST_DIR)


def get_store(
    collection_name: str, embeddings=None, persist_dir: str | None = None
) -> Chroma:
    return Chroma(
        collection_name=normalize_collection_name(collection_name),
        embedding_function=embeddings or get_embeddings(),
        persist_directory=persist_dir or config.CHROMA_PERSIST_DIR,
    )


def list_collections(persist_dir: str | None = None) -> list[str]:
    return sorted(c.name for c in _client(persist_dir).list_collections())


def collection_size(collection_name: str, persist_dir: str | None = None) -> int:
    try:
        collection = _client(persist_dir).get_collection(
            normalize_collection_name(collection_name)
        )
    except Exception:
        return 0
    return collection.count()


def add_chunks(
    collection_name: str,
    records: list[dict],
    embeddings=None,
    persist_dir: str | None = None,
) -> int:
    """Append chunk records to a collection, creating it if needed."""
    if not records:
        return 0
    store = get_store(collection_name, embeddings, persist_dir)
    store.add_texts(
        texts=[r["text"] for r in records],
        metadatas=[r["metadata"] for r in records],
    )
    return len(records)


def similarity_search(
    collection_name: str,
    query: str,
    k: int = config.TOP_K,
    embeddings=None,
    persist_dir: str | None = None,
    reranker=None,
):
    """Top-k retrieval against one collection (FR5), reranked and gated:

    1. Pull a candidate pool wider than k by vector similarity.
    2. Re-score every candidate with a cross-encoder, which reads the query
       and the chunk together instead of comparing embedding vectors, and
       order by that. Skipped when RERANK_ENABLED is false.
    3. If the best candidate still scores below SIMILARITY_THRESHOLD,
       return nothing: the collection has no answer to this question, and
       the caller refuses without spending an LLM call (FR6).
    """
    store = get_store(collection_name, embeddings, persist_dir)
    if not config.RERANK_ENABLED:
        return store.similarity_search(query, k=k)

    candidates = store.similarity_search(query, k=max(k, config.RERANK_FETCH_K))
    if not candidates:
        return []

    reranker = reranker or get_reranker()
    scores = reranker.rerank(query, [doc.page_content for doc in candidates])
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    if ranked[0][1] < config.SIMILARITY_THRESHOLD:
        return []
    return [doc for doc, _ in ranked[:k]]


def delete_collection(collection_name: str, persist_dir: str | None = None) -> None:
    try:
        _client(persist_dir).delete_collection(
            normalize_collection_name(collection_name)
        )
    except Exception:
        pass
