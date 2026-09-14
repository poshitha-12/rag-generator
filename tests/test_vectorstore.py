"""FR2 — named collections coexist independently, plus the retrieval
quality gates (similarity threshold + semantic rerank) that sit in front
of generation."""

from app import config, vectorstore
from app.ingestion import ingest_documents


def _docs(prefix: str) -> list[tuple[str, bytes]]:
    return [
        (
            f"{prefix}.txt",
            f"{prefix} alpha bravo charlie delta. "
            f"{prefix} echo foxtrot golf hotel.".encode(),
        )
    ]


def test_collection_isolation(embeddings, reranker, persist_dir):
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
        "set-one",
        "quartz alpha",
        k=5,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert hits and all("basalt" not in d.page_content for d in hits)

    hits = vectorstore.similarity_search(
        "set-two",
        "basalt echo",
        k=5,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert hits and all("quartz" not in d.page_content for d in hits)

    # Appending to one collection does not change the size of the other.
    before = vectorstore.collection_size("set-two", persist_dir)
    ingest_documents(
        "set-one", _docs("gneiss"), embeddings=embeddings, persist_dir=persist_dir
    )
    assert vectorstore.collection_size("set-two", persist_dir) == before
    assert vectorstore.collection_size("set-one", persist_dir) > before


# One file per topic, so each lands in its own chunk and the reranker has
# genuinely competing candidates to order.
RERANK_DOCS = [
    ("rota.txt", b"Alpha bravo charlie: the dispatch rota is published every Monday."),
    (
        "refunds.txt",
        b"Refunds are issued to the original payment method within ten days.",
    ),
    (
        "overtime.txt",
        b"Bravo charlie delta: overtime is approved by the shift supervisor.",
    ),
]


class StubReranker:
    """Scores one keyword above everything else, so the test can force an
    order vector similarity would never produce on its own - the point is
    that the cross-encoder's verdict wins, not what it happens to think."""

    def __init__(self, keyword: str):
        self.keyword = keyword

    def rerank(self, query, documents, batch_size=64, **kwargs):
        for doc in documents:
            yield 1.0 if self.keyword.lower() in doc.lower() else 0.0


def test_rerank_decides_final_order_not_vector_distance(
    embeddings, persist_dir, monkeypatch
):
    """The cross-encoder, not raw vector distance, decides the final order."""
    ingest_documents(
        "manuals", RERANK_DOCS, embeddings=embeddings, persist_dir=persist_dir
    )
    # Open the coarse gate so this exercises reranking alone: the vector
    # threshold runs first, and set too high it starves the reranker of the
    # very candidates it exists to re-score.
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 0.0)
    question = "refunds payment method"

    # Vector similarity alone puts the refunds chunk first...
    by_vector = vectorstore.similarity_search(
        "manuals",
        question,
        k=3,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=StubReranker("refunds"),
    )
    assert by_vector[0].metadata["source"] == "refunds.txt"

    # ...but a reranker that prefers a different chunk overrides it.
    by_rerank = vectorstore.similarity_search(
        "manuals",
        question,
        k=3,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=StubReranker("overtime"),
    )
    assert by_rerank[0].metadata["source"] == "overtime.txt", (
        "the reranker's top-scored chunk must lead the results"
    )


def test_rerank_score_threshold_drops_weak_chunks(
    embeddings, reranker, persist_dir, monkeypatch
):
    """The optional rerank-score gate removes chunks the cross-encoder
    scores below the floor, even though they cleared vector similarity."""
    ingest_documents(
        "manuals", RERANK_DOCS, embeddings=embeddings, persist_dir=persist_dir
    )
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 0.0)

    monkeypatch.setattr(config, "RERANK_SCORE_THRESHOLD", None)
    unfiltered = vectorstore.similarity_search(
        "manuals",
        "refunds payment method",
        k=5,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )

    # FakeReranker scores by word overlap, so a floor of 2 keeps only the
    # chunk sharing two or more words with the query.
    monkeypatch.setattr(config, "RERANK_SCORE_THRESHOLD", 2.0)
    filtered = vectorstore.similarity_search(
        "manuals",
        "refunds payment method",
        k=5,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert len(filtered) < len(unfiltered), "the floor must drop weak chunks"
    assert all("Refunds" in d.page_content for d in filtered)


def test_user_supplied_names_are_slugified_safely():
    assert vectorstore.normalize_collection_name("My Docs! 2024") == "My-Docs-2024"
    assert len(vectorstore.normalize_collection_name("a")) >= 3
    assert vectorstore.normalize_collection_name("") == "collection"
