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
        # Cosine distance keeps relevance scores on a fixed [0, 1] scale
        # independent of embedding dimensionality/model, so
        # SIMILARITY_THRESHOLD means the same thing across embedding
        # models. Chroma's default (l2) relevance score is not
        # comparably calibrated - e.g. it scores a correct match well
        # below any sane threshold for some embedding spaces.
        collection_metadata={"hnsw:space": "cosine"},
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
    """Top-k retrieval against one collection (FR5), narrowed by a
    similarity-score floor and a semantic rerank pass (FR6 hardening):

    1. Pull a wider candidate pool by vector similarity.
    2. Drop anything below SIMILARITY_THRESHOLD - a cheap gate against
       off-topic questions, before any cross-encoder or LLM work happens.
    3. Re-score the survivors with a cross-encoder, which reads the query
       and each chunk together instead of comparing embedding vectors, and
       keep the top k. Skipped when RERANK_ENABLED is false.
    4. Optionally drop anything under RERANK_SCORE_THRESHOLD - the sharper
       of the two gates, but corpus-specific, so it is off by default.
    """
    store = get_store(collection_name, embeddings, persist_dir)
    fetch_k = max(k, config.RERANK_FETCH_K) if config.RERANK_ENABLED else k

    scored = store.similarity_search_with_relevance_scores(query, k=fetch_k)
    candidates = [doc for doc, score in scored if score >= config.SIMILARITY_THRESHOLD]
    if not candidates or not config.RERANK_ENABLED:
        return candidates[:k]

    reranker = reranker or get_reranker()
    rerank_scores = reranker.rerank(query, [doc.page_content for doc in candidates])
    ranked = sorted(zip(candidates, rerank_scores), key=lambda pair: pair[1], reverse=True)
    if config.RERANK_SCORE_THRESHOLD is not None:
        ranked = [p for p in ranked if p[1] >= config.RERANK_SCORE_THRESHOLD]
    return [doc for doc, _ in ranked[:k]]


def delete_collection(collection_name: str, persist_dir: str | None = None) -> None:
    try:
        _client(persist_dir).delete_collection(
            normalize_collection_name(collection_name)
        )
    except Exception:
        pass
