"""NFR4 — measure answer *quality* against the real configured LLM.

The pytest suite checks that the grounding mechanism is enforced: that
retrieval feeds the prompt, that the threshold refuses, that citations are
attached. None of that says whether the answers are actually right. This
script asks the real model real questions about the real sample documents
and checks the answers against what those documents actually say.

Not part of `make verify`: it needs a live API key and spends tokens.

    python eval/run_eval.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, rag_chain, vectorstore  # noqa: E402
from app.ingestion import SUPPORTED_EXTENSIONS, ingest_documents  # noqa: E402

EVAL_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EVAL_SET = EVAL_DIR / "eval_set.json"
RESULTS = EVAL_DIR / "RESULTS.md"
# Kept out of the app's own store so an eval run never disturbs whatever
# collections the user has ingested through the UI.
PERSIST_DIR = str(EVAL_DIR / ".chroma_eval")


def load_collections() -> dict[str, list[tuple[str, bytes]]]:
    """Each sub-directory of data/ is one collection, named after it."""
    collections = {}
    for directory in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        files = sorted(
            f
            for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if files:
            collections[directory.name] = [(f.name, f.read_bytes()) for f in files]
    return collections


def ingest(collections: dict[str, list[tuple[str, bytes]]]) -> None:
    """Rebuild each collection from scratch so a run is reproducible.

    Calls the ingestion path directly rather than going through Redis -
    the queue is about not blocking the UI, which no script cares about.
    """
    for name, documents in collections.items():
        vectorstore.delete_collection(name, persist_dir=PERSIST_DIR)
        result = ingest_documents(name, documents, persist_dir=PERSIST_DIR)
        print(
            f"  ingested {name}: {result['files']} files, "
            f"{result['chunks']} chunks ({', '.join(n for n, _ in documents)})"
        )


def grade(row: dict, result: dict, known_sources: set[str]) -> tuple[bool, str]:
    """Score one answer. Returns (passed, human-readable reason)."""
    # "Refused" is whatever rag_chain already says it is - one definition,
    # not a second one invented here.
    refused = not result["grounded"]

    if row["should_refuse"]:
        if refused:
            return True, "refused as expected"
        return False, "answered a question the collection cannot support"

    if refused:
        return False, "refused a question the documents do answer"

    answer = result["answer"].lower()
    missing = [k for k in row["expected_answer_keywords"] if k.lower() not in answer]
    if missing:
        return False, f"answer missing {', '.join(repr(m) for m in missing)}"

    cited = {s["source"] for s in result["sources"]}
    stray = cited - known_sources
    if stray:
        return False, f"cited outside the collection: {', '.join(sorted(stray))}"
    if not cited:
        return False, "no sources cited"
    return True, "correct, cited in-collection"


def main() -> int:
    rows = json.loads(EVAL_SET.read_text())
    collections = load_collections()
    missing = {r["collection"] for r in rows} - set(collections)
    if missing:
        print(f"No documents found in data/ for: {', '.join(sorted(missing))}")
        return 1

    provider = config.LLM_PROVIDER
    model = config.OPENAI_MODEL if provider == "openai" else config.ANTHROPIC_MODEL
    print(f"Evaluating against {provider}:{model}\n")
    ingest(collections)

    filenames = {
        name: {n for n, _ in documents} for name, documents in collections.items()
    }

    print()
    results = []
    for row in rows:
        result = rag_chain.answer_question(
            row["collection"], row["question"], persist_dir=PERSIST_DIR
        )
        passed, reason = grade(row, result, filenames[row["collection"]])
        results.append((row, result, passed, reason))
        print(f"  {'PASS' if passed else 'FAIL'}  {row['question'][:60]:62} {reason}")

    passes = sum(1 for *_, passed, _ in results if passed)
    summary = f"{passes}/{len(results)} passed"
    print(f"\n{summary}")
    write_results(results, summary, provider, model, collections)
    print(f"Wrote {RESULTS.relative_to(ROOT)}")
    return 0 if passes == len(results) else 1


def caveats(collections) -> list[str]:
    """State what these numbers do *not* prove.

    A collection with no more chunks than top-k hands every chunk to every
    question, so a pass there says the model read the documents correctly
    but says nothing about whether retrieval ranked anything well. Worth
    saying out loud rather than letting a high score imply otherwise.
    """
    saturated = [
        (name, size)
        for name in collections
        if (size := vectorstore.collection_size(name, PERSIST_DIR)) <= config.TOP_K
    ]
    if not saturated:
        return []
    listed = "; ".join(f"`{n}` ({s} chunks)" for n, s in saturated)
    return [
        "> **Caveat — retrieval is not meaningfully exercised for every "
        f"collection.** With top-k {config.TOP_K}: {listed}. A collection no "
        "larger than top-k returns all of its chunks for every question, so "
        "those rows measure whether the model answers correctly from the "
        "documents, not whether retrieval ranked the right chunk first. Add "
        "more documents to test ranking.",
        "",
    ]


def write_results(results, summary, provider, model, collections) -> None:
    ingested = "; ".join(
        f"`{name}` ({', '.join(n for n, _ in docs)})" for name, docs in collections.items()
    )
    lines = [
        "# Evaluation results",
        "",
        f"**{summary}** against `{provider}:{model}`, "
        f"top-k {config.TOP_K}, rerank "
        f"{'on' if config.RERANK_ENABLED else 'off'} "
        f"(`{config.RERANK_MODEL}`), relevance floor "
        f"`{config.SIMILARITY_THRESHOLD}`.",
        "",
        f"Collections ingested from `data/`: {ingested}.",
        "",
        "Generated by `python eval/run_eval.py` — regenerate after changing the",
        "documents, the retrieval settings or the model. Answers come from the",
        "real LLM, so exact wording varies between runs.",
        "",
        *caveats(collections),
        "| # | Collection | Question | Expected | Result | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for i, (row, result, passed, reason) in enumerate(results, 1):
        expected = (
            "refusal"
            if row["should_refuse"]
            else ", ".join(f"`{k}`" for k in row["expected_answer_keywords"])
        )
        cited = ", ".join(
            sorted({f"{s['source']}#{s['chunk_index']}" for s in result["sources"]})
        )
        notes = reason if not passed else (cited or reason)
        lines.append(
            f"| {i} | `{row['collection']}` | {row['question']} | {expected} "
            f"| {'PASS' if passed else '**FAIL**'} | {notes} |"
        )
    lines.append("")
    RESULTS.write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
