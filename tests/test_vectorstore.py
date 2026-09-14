"""FR2 — named collections coexist independently."""

from app import vectorstore
from app.ingestion import ingest_documents


def _docs(prefix: str) -> list[tuple[str, bytes]]:
    return [
        (
            f"{prefix}.txt",
            f"{prefix} alpha bravo charlie delta. "
            f"{prefix} echo foxtrot golf hotel.".encode(),
        )
    ]


def test_collection_isolation(embeddings, persist_dir):
    """Two uploads into two names produce two independent indexes: each
    collection retrieves only its own chunks, and appending to one leaves
    the other untouched."""
    first = ingest_documents(
        "set-one", _docs("quartz"), embeddings=embeddings, persist_dir=persist_dir
    )
    second = ingest_documents(
        "set-two", _docs("basalt"), embeddings=embeddings, persist_dir=persist_dir
    )
    assert first["chunks"] and second["chunks"]

    assert set(vectorstore.list_collections(persist_dir)) == {"set-one", "set-two"}

    hits = vectorstore.similarity_search(
        "set-one", "quartz alpha", k=5, embeddings=embeddings, persist_dir=persist_dir
    )
    assert hits and all("basalt" not in d.page_content for d in hits)

    hits = vectorstore.similarity_search(
        "set-two", "basalt echo", k=5, embeddings=embeddings, persist_dir=persist_dir
    )
    assert hits and all("quartz" not in d.page_content for d in hits)

    # Appending to one collection does not change the size of the other.
    before = vectorstore.collection_size("set-two", persist_dir)
    ingest_documents(
        "set-one", _docs("gneiss"), embeddings=embeddings, persist_dir=persist_dir
    )
    assert vectorstore.collection_size("set-two", persist_dir) == before
    assert vectorstore.collection_size("set-one", persist_dir) > before


def test_user_supplied_names_are_slugified_safely():
    assert vectorstore.normalize_collection_name("My Docs! 2024") == "My-Docs-2024"
    assert len(vectorstore.normalize_collection_name("a")) >= 3
    assert vectorstore.normalize_collection_name("") == "collection"
