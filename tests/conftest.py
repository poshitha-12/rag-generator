"""Shared test fixtures.

Unit tests never load the real embedding model or call a real LLM - both
are injected - so the whole suite stays well inside NFR2's 30s budget.
"""

import hashlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "data"


class FakeEmbeddings:
    """Deterministic bag-of-words embedding: no model download, but similar
    text still lands near similar text, so retrieval is meaningfully tested."""

    dimension = 64

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in text.lower().split():
            token = token.strip(".,!?;:'\"()")
            if not token:
                continue
            index = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimension
            vec[index] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


class FakeReranker:
    """Deterministic keyword-overlap reranker: no model download, but a
    chunk sharing more words with the query still scores higher."""

    def rerank(self, query, documents, batch_size=64, **kwargs):
        q_tokens = {t.strip(".,!?;:'\"()") for t in query.lower().split()}
        for doc in documents:
            d_tokens = {t.strip(".,!?;:'\"()") for t in doc.lower().split()}
            yield float(len(q_tokens & d_tokens))


@pytest.fixture
def embeddings():
    return FakeEmbeddings()


@pytest.fixture
def reranker():
    return FakeReranker()


@pytest.fixture
def persist_dir(tmp_path):
    return str(tmp_path / "chroma")
