"""Retrieval + grounded generation (FR4, FR5, FR6)."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app import config, vectorstore

NO_ANSWER = (
    "I don't know - the retrieved context doesn't contain the answer to that."
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions strictly from the provided context passages.\n"
            "Rules:\n"
            "1. Use only the context below. Never use outside knowledge and never "
            "guess.\n"
            "2. If the context does not contain the answer, reply with exactly: "
            f"{NO_ANSWER}\n"
            "3. When you do answer, cite the passages you used inline as "
            "[source: <file name>, chunk <index>].",
        ),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ]
)


def get_llm():
    """Build the chat model lazily so the app boots without a key present."""
    if config.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=config.OPENAI_MODEL, temperature=config.LLM_TEMPERATURE)
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=config.ANTHROPIC_MODEL, temperature=config.LLM_TEMPERATURE
    )


def format_context(docs) -> str:
    """Render retrieved chunks with the citation labels the prompt asks for."""
    return "\n\n".join(
        "[source: {source}, chunk {index}]\n{text}".format(
            source=doc.metadata.get("source", "unknown"),
            index=doc.metadata.get("chunk_index", 0),
            text=doc.page_content,
        )
        for doc in docs
    )


def _citation(doc) -> dict:
    return {
        "source": doc.metadata.get("source", "unknown"),
        "chunk_index": doc.metadata.get("chunk_index", 0),
        "text": doc.page_content,
    }


def answer_question(
    collection_name: str,
    question: str,
    k: int = config.TOP_K,
    llm=None,
    embeddings=None,
    persist_dir: str | None = None,
) -> dict:
    """Answer a question against one collection, grounded in top-k chunks."""
    docs = vectorstore.similarity_search(
        collection_name, question, k=k, embeddings=embeddings, persist_dir=persist_dir
    )
    if not docs:
        # Nothing retrieved - refuse without spending an LLM call (FR6).
        return {"answer": NO_ANSWER, "sources": [], "grounded": False}

    llm = llm or get_llm()
    message = llm.invoke(
        PROMPT.format_messages(context=format_context(docs), question=question)
    )
    answer = getattr(message, "content", message)
    if isinstance(answer, list):  # some providers return content blocks
        answer = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in answer
        )
    answer = str(answer).strip()
    refused = answer.startswith(NO_ANSWER[:20])
    return {
        "answer": answer,
        "sources": [] if refused else [_citation(d) for d in docs],
        "grounded": not refused,
    }
