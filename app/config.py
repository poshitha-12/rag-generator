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

# --- retrieval quality (FR6 hardening) --------------------------------------
# Vector-similarity candidates below this relevance score (0-1, higher is
# closer) are dropped before they ever reach the LLM - a cheap first gate
# against off-topic questions, on top of the prompt-instructed refusal.
# Deliberately loose: this gate runs before reranking, so raising it far
# starves the reranker of the candidates it exists to re-score. Measured
# with the default embedding model, on-topic questions land around 0.65-0.70
# and off-topic ones around 0.40-0.50, so this catches only true garbage -
# RERANK_SCORE_THRESHOLD below is the sharper instrument.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.2"))
# A second-stage cross-encoder rerank of the surviving candidates, more
# accurate than raw vector distance because it scores the query against
# each candidate directly instead of via embedding-space proximity.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").strip().lower() not in (
    "false",
    "0",
    "no",
)
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
# How many vector-search candidates to pull before threshold + rerank narrow
# them down to TOP_K - wider than TOP_K so reranking has something to sort.
RERANK_FETCH_K = _int("RERANK_FETCH_K", 20)
# Optional second gate on the cross-encoder's own score (a raw logit -
# higher is more relevant). It separates on-topic from off-topic far more
# sharply than vector distance does, but the useful cut-off depends on the
# model and the corpus, so it ships off (blank) and is opt-in after you
# calibrate against your own documents. See README.
_rerank_floor = os.getenv("RERANK_SCORE_THRESHOLD", "").strip()
RERANK_SCORE_THRESHOLD = float(_rerank_floor) if _rerank_floor else None

# --- generation ------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
