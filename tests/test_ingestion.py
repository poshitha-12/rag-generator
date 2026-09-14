"""FR1, FR7 (nothing document-specific in app/) and FR8 (boundary-aware chunking)."""

import re

from conftest import APP_DIR, DATA_DIR

from app.ingestion import chunk_documents, chunk_text, load_document

TERMINATORS = (".", "!", "?", '"', ":", ";")


# --- FR1 / FR7 -------------------------------------------------------------
def test_no_hardcoded_documents():
    """No sample document name, path or topic word may appear in app/.

    The sample sets under data/ exist only to demo the app; if any of their
    names or subject matter leak into application code, switching domains
    would stop being a zero-code-change operation.
    """
    # File and directory names are derived from what is actually in data/,
    # so adding a sample set automatically widens the check.
    forbidden = {
        part.lower()
        for path in DATA_DIR.rglob("*")
        if path.name != ".gitkeep"
        for part in (path.name, path.stem)
    }
    # Plus the distinctive subject matter of those sets. Listing these in a
    # test is fine - the rule is that they must not appear in app/.
    forbidden |= {"handbook", "faq", "northwind", "tidewater", "ts-40", "logistics"}

    assert len(forbidden) > 4, "sample document sets missing from data/"

    offenders = [
        f"{source.name}: {term}"
        for source in APP_DIR.rglob("*.py")
        for term in forbidden
        if term in source.read_text().lower()
    ]
    assert not offenders, f"document-specific references in app/: {offenders}"

    # ...and no absolute filesystem paths either (NFR3).
    for source in APP_DIR.rglob("*.py"):
        assert not re.search(r"['\"]/(Users|home|var|tmp)/", source.read_text()), (
            f"absolute path hardcoded in {source.name}"
        )


def test_loader_handles_plain_text_and_rejects_unknown_types():
    assert "hello" in load_document("notes.txt", b"hello world")
    try:
        load_document("archive.zip", b"")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported extension should raise")


# --- FR8 -------------------------------------------------------------------
def test_chunk_boundaries_are_sentence_aware():
    """Chunks split at paragraph then sentence boundaries, never mid-sentence
    unless a single sentence is itself larger than the chunk size."""
    paragraph_a = (
        "Alpha covers the first topic in some detail. "
        "It continues with a second sentence about the same topic. "
        "A third sentence closes the paragraph off."
    )
    paragraph_b = (
        "Beta introduces an unrelated topic entirely. "
        "It also has a follow-up sentence. "
        "And a final one to finish."
    )
    text = f"{paragraph_a}\n\n{paragraph_b}"

    # Both paragraphs fit: prefer the paragraph break over any inner split.
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=20)
    assert chunks == [paragraph_a, paragraph_b]

    # Too small for a whole paragraph: fall back to sentence boundaries only.
    chunks = chunk_text(text, chunk_size=120, chunk_overlap=20)
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.endswith(TERMINATORS), f"chunk ends mid-sentence: {chunk!r}"
        assert len(chunk) <= 120

    # Last resort: one sentence longer than the chunk size may be cut, but
    # only that sentence - and the cut happens at a space, not mid-word.
    long_sentence = " ".join(f"word{i}" for i in range(60)) + "."
    chunks = chunk_text(f"Short opener here. {long_sentence}", chunk_size=100,
                        chunk_overlap=0)
    assert any(not c.endswith(TERMINATORS) for c in chunks), (
        "an oversized sentence must still be split"
    )
    words = set(f"word{i}" for i in range(60)) | {"Short", "opener", "here.", "word59."}
    for chunk in chunks:
        for token in chunk.split():
            assert token in words, f"split landed mid-word: {token!r}"


def test_chunk_documents_attaches_citation_metadata():
    records = chunk_documents([("report.txt", b"One sentence. Two sentence.")])
    assert records
    assert records[0]["metadata"] == {"source": "report.txt", "chunk_index": 0}
