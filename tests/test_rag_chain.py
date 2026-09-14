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


def test_grounded_answer_and_refusal(embeddings, reranker, persist_dir):
    ingest_documents(
        "policies", DOCS, embeddings=embeddings, persist_dir=persist_dir
    )

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

    # FR6 — context that doesn't contain the answer produces a refusal,
    # not an invented one, and no sources are cited.
    llm = RecordingLLM("orbital mechanics", "...")
    result = rag_chain.answer_question(
        "policies",
        "What is the delta-v budget for a lunar transfer?",
        k=4,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert result["answer"] == rag_chain.NO_ANSWER
    assert result["sources"] == []
    assert not result["grounded"]


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


def test_off_topic_question_refuses_below_similarity_threshold(
    embeddings, reranker, persist_dir, monkeypatch
):
    """FR6 hardening — a query whose best match is still a poor semantic
    fit gets refused by the similarity-threshold gate, without ever
    reaching the LLM (the reranker never runs either, since nothing
    clears the gate for it to re-score)."""
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 0.9)
    ingest_documents("policies", DOCS, embeddings=embeddings, persist_dir=persist_dir)
    llm = RecordingLLM("anything", "should not be reached")
    result = rag_chain.answer_question(
        "policies",
        "What is the airspeed velocity of an unladen swallow?",
        k=4,
        llm=llm,
        embeddings=embeddings,
        persist_dir=persist_dir,
        reranker=reranker,
    )
    assert result["answer"] == rag_chain.NO_ANSWER
    assert result["sources"] == []
    assert llm.prompts == [], "no LLM call should be made below the similarity floor"
