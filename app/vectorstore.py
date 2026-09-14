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


def get_embeddings():
    """Local (ONNX, no API key) embeddings, loaded once per process."""
    global _embeddings
    if _embeddings is None:
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

        options = {"model_name": config.EMBEDDING_MODEL} if config.EMBEDDING_MODEL else {}
        _embeddings = FastEmbedEmbeddings(**options)
    return _embeddings


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
):
    """Top-k retrieval against one collection (FR5)."""
    store = get_store(collection_name, embeddings, persist_dir)
    return store.similarity_search(query, k=k)


def delete_collection(collection_name: str, persist_dir: str | None = None) -> None:
    try:
        _client(persist_dir).delete_collection(
            normalize_collection_name(collection_name)
        )
    except Exception:
        pass
