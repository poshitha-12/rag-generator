"""Loading and boundary-aware chunking of uploaded documents.

Covers FR1/FR7 (any document set, supplied at runtime) and FR8 (splits
respect paragraph then sentence boundaries). Documents are passed around
as (filename, bytes) pairs and parsed in memory, so nothing here depends
on a file living at a particular path.
"""

from __future__ import annotations

import io

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import config, vectorstore

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")

# FR8: preferred split points, most structural first. Paragraph breaks win;
# then single newlines; then sentence terminators; a bare space (or a raw
# character cut) is only reached when one sentence is itself oversized.
SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]


def _extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def load_document(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded file's raw bytes."""
    ext = _extension(filename)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in document.paragraphs)
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {ext or filename}")


def chunk_text(
    text: str,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> list[str]:
    """Split text at the most structural boundary that fits (FR8).

    `keep_separator="end"` keeps the terminator attached to the chunk it
    closes, so a chunk ends on a full sentence rather than losing the
    punctuation to the split.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        keep_separator="end",
        strip_whitespace=True,
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def chunk_documents(documents: list[tuple[str, bytes]]) -> list[dict]:
    """Turn uploaded files into embeddable records with citation metadata."""
    records: list[dict] = []
    for filename, data in documents:
        text = load_document(filename, data)
        for index, chunk in enumerate(chunk_text(text)):
            records.append(
                {
                    "text": chunk,
                    "metadata": {"source": filename, "chunk_index": index},
                }
            )
    return records


def ingest_documents(
    collection_name: str,
    documents: list[tuple[str, bytes]],
    embeddings=None,
    persist_dir: str | None = None,
) -> dict:
    """Chunk + embed documents into a named collection (FR2).

    This is the unit of work the queue runs; it is safe to call directly
    in tests or from a worker process.
    """
    records = chunk_documents(documents)
    vectorstore.add_chunks(
        collection_name, records, embeddings=embeddings, persist_dir=persist_dir
    )
    return {
        "collection": vectorstore.normalize_collection_name(collection_name),
        "files": len(documents),
        "chunks": len(records),
    }
