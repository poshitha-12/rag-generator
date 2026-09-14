"""Runtime configuration. Everything here is env-driven so the app is
generic over whatever documents are uploaded (NFR3 — no document names,
paths or topic strings baked into application code)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- storage ---------------------------------------------------------------
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_store")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = os.getenv("QUEUE_NAME", "default")

# --- embedding + chunking --------------------------------------------------
# Blank means "use the embedding library's own default model".
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
CHUNK_SIZE = _int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 100)
TOP_K = _int("TOP_K", 5)

# --- retrieval quality ------------------------------------------------------
# A cross-encoder rerank of the vector-search candidates, more accurate than
# raw vector distance because it scores the query against each candidate
# directly instead of via embedding-space proximity.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").strip().lower() not in (
    "false",
    "0",
    "no",
)
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
# How many vector-search candidates to pull before reranking narrows them
# back down to TOP_K - wider than TOP_K so reranking has something to sort.
RERANK_FETCH_K = _int("RERANK_FETCH_K", 20)
# The relevance floor behind FR6's refusal: if the best chunk the reranker
# can find scores below this, the question is treated as unanswerable from
# the collection and refused without an LLM call. A raw cross-encoder logit,
# higher being more relevant. Measured against the sample corpus with the
# default model: on-topic questions scored -4.9 to +5.8, off-topic ones
# -11.4 to -11.0, so this sits mid-gap with margin either side. Recalibrate
# if you change RERANK_MODEL.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "-8.0"))

# --- generation ------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
