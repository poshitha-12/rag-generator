"""FR5 (grounded, cited answers) and FR6 (refuses instead of fabricating)."""

from app import config, rag_chain
from app.ingestion import ingest_documents


class RecordingLLM:
    """Stand-in for Claude/GPT. It honours the grounding contract the prompt
    states - answer only from the context, otherwise refuse - so the test
    exercises the plumbing (what context reaches the model, what comes back)
    without a network call."""

    def __init__(self, keyword: str, answer: str):
        self.keyword = keyword
        self.answer = answer
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append("\n".join(m.content for m in messages))
        context = messages[-1].content
        if self.keyword.lower() in context.lower():
            return type("Msg", (), {"content": self.answer})()
        return type("Msg", (), {"content": rag_chain.NO_ANSWER})()


DOCS = [
    (
        "policy.txt",
        b"The support desk answers within one business day. "
        b"Escalations are handled by the on-call engineer.\n\n"
        b"Replacement hardware ships the next business day for premium plans.",
    )
]


def test_grounded_answer_and_refusal(embeddings, reranker, persist_dir, monkeypatch):
    ingest_documents(
        "policies", DOCS, embeddings=embeddings, persist_dir=persist_dir
    )
    # The shipped floor is calibrated for the real cross-encoder's logits;
    # FakeReranker scores word overlap, so set the floor on that scale -
    # one shared word or better.
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 1.0)

    # FR5 — answered from retrieved chunks, with file name + chunk index.
    llm = RecordingLLM("business day", "Within one business day [source: policy.txt, chunk 0].")
    result = rag_chain.answer_question(
        "policies",
        "How quickly does the desk respond?",
        k=4,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert result["grounded"]
    assert result["sources"], "a grounded answer must cite its chunks"
    assert {"source", "chunk_index"} <= set(result["sources"][0])
    assert result["sources"][0]["source"] == "policy.txt"

    # The model only ever saw retrieved chunks, labelled for citation.
    prompt = llm.prompts[0]
    assert "[source: policy.txt, chunk 0]" in prompt
    assert "business day" in prompt
    assert rag_chain.NO_ANSWER in prompt, "prompt must instruct the refusal"

    # FR6 — an off-domain question is refused by the threshold, before the
    # LLM is reached: that comparison is the primary mechanism, and unlike
    # a prompt instruction it can't be talked out of its answer.
    llm = RecordingLLM("orbital mechanics", "should not be reached")
    result = rag_chain.answer_question(
        "policies",
        "Quel est le budget delta-v pour une injection lunaire?",
        k=4,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert result["answer"] == rag_chain.NO_ANSWER
    assert result["sources"] == []
    assert not result["grounded"]
    assert llm.prompts == [], "the threshold must refuse before the LLM call"


def test_empty_collection_refuses_without_calling_the_model(embeddings, reranker, persist_dir):
    """Nothing retrieved means nothing to ground an answer in (FR6)."""
    ingest_documents("seeded", DOCS, embeddings=embeddings, persist_dir=persist_dir)
    llm = RecordingLLM("anything", "should not be reached")
    result = rag_chain.answer_question(
        "empty-set",
        "Anything at all?",
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert result["answer"] == rag_chain.NO_ANSWER
    assert llm.prompts == [], "no LLM call should be made with no context"


def test_prompt_refusal_backs_up_the_threshold(embeddings, reranker, persist_dir):
    """FR6's second line of defense — a question close enough to the corpus
    to clear the threshold, but whose retrieved context still doesn't
    answer it, is refused by the model on the prompt's instruction. The
    LLM *is* called here; that's the point of the layering."""
    ingest_documents("policies", DOCS, embeddings=embeddings, persist_dir=persist_dir)
    llm = RecordingLLM("orbital mechanics", "should not be invented")
    result = rag_chain.answer_question(
        "policies",
        "Which business day does the support desk ship hardware returns on?",
        k=4,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert llm.prompts, "this question should clear the threshold and reach the LLM"
    assert result["answer"] == rag_chain.NO_ANSWER
    assert result["sources"] == []
    assert not result["grounded"]


class StubReranker:
    """Scores one keyword above all else. The fakes used elsewhere in the
    suite are both lexical (hashed bag-of-words embeddings, word-overlap
    reranking), so they never disagree - and the real cross-encoder is an
    80MB download that NFR2's 30s budget rules out of a unit test. So the
    ordering test forces the disagreement explicitly: what it proves is
    that the reranker's verdict, not vector distance, sets the final
    order - not that the real model ranks any particular way."""

    def __init__(self, keyword: str):
        self.keyword = keyword

    def rerank(self, query, documents, batch_size=64, **kwargs):
        for doc in documents:
            yield 5.0 if self.keyword.lower() in doc.lower() else 0.0


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


def test_reranking_changes_chunk_order(embeddings, persist_dir):
    """Reranking, not vector similarity, decides which chunks reach the
    prompt and in what order."""
    ingest_documents(
        "manuals", RERANK_DOCS, embeddings=embeddings, persist_dir=persist_dir
    )
    question = "refunds payment method"

    # Vector similarity ranks the refunds chunk top for this question...
    llm = RecordingLLM("Refunds", "Within ten days [source: refunds.txt, chunk 0].")
    rag_chain.answer_question(
        "manuals",
        question,
        k=3,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=StubReranker("refunds"),
    )
    assert llm.prompts[0].index("Refunds") < llm.prompts[0].index("overtime")

    # ...but a reranker that prefers the overtime chunk reorders the
    # context the model actually sees.
    llm = RecordingLLM("overtime", "Approved by the supervisor [source: overtime.txt, chunk 0].")
    result = rag_chain.answer_question(
        "manuals",
        question,
        k=3,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=StubReranker("overtime"),
    )
    assert llm.prompts[0].index("overtime") < llm.prompts[0].index("Refunds"), (
        "the reranker's top-scored chunk must lead the prompt context"
    )
    assert result["sources"][0]["source"] == "overtime.txt"
