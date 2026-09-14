"""NFR4 — measure answer *quality* against the real configured LLM.

The pytest suite checks that the grounding mechanism is enforced: that
retrieval feeds the prompt, that the threshold refuses, that citations are
attached. None of that says whether the answers are actually right. This
script asks the real model real questions about the real sample documents
and checks the answers against what those documents actually say.

Two independent signals per answerable question, not one conflated
pass/fail: retrieval-hit (did the expected file come back in the top-k)
and answer-correctness (does the answer contain the expected facts).
Refusal questions are graded on rag_chain's own "grounded" flag - one
definition of refused, not a second one invented here.

On top of that, RAGAS scores the same run with an LLM-as-judge, using the
same model and embeddings the app itself is configured with - not RAGAS's
own defaults. Two groups, because half the metrics need a ground-truth
answer and half don't:

  faithfulness, answer_relevancy          every answered row
  context_precision, context_recall,      only rows carrying an optional
  answer_correctness                      `reference_answer` in eval_set.json

`should_refuse` rows are skipped entirely - there is no answer for a judge
to read - and keep the refusal check, which already works.

Not part of `make verify`: this needs a live API key and spends tokens,
RAGAS meaningfully more, since each metric is its own judge call per row.

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
# Metrics that only need the question, answer and retrieved chunks...
REFERENCE_FREE_METRICS = ("faithfulness", "answer_relevancy")
# ...and those that also need a ground-truth `reference_answer`.
REFERENCE_BASED_METRICS = ("context_precision", "context_recall", "answer_correctness")
RAGAS_METRICS = REFERENCE_FREE_METRICS + REFERENCE_BASED_METRICS


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


def grade(row: dict, result: dict) -> dict:
    """Score one answer against two independent signals for answerable
    questions - retrieval_hit and answer_correct - or one for refusal
    questions. Returns a dict always carrying "passed" and "reason"."""
    refused = not result["grounded"]

    if row["should_refuse"]:
        passed = refused
        reason = "refused as expected" if passed else "answered a question the collection cannot support"
        return {"passed": passed, "retrieval_hit": None, "answer_correct": None, "reason": reason}

    if refused:
        return {
            "passed": False,
            "retrieval_hit": False,
            "answer_correct": False,
            "reason": "refused a question the documents do answer",
        }

    cited = {s["source"] for s in result["sources"]}
    retrieval_hit = row["expected_source"] in cited

    answer = result["answer"].lower()
    missing = [k for k in row["expected_answer_keywords"] if k.lower() not in answer]
    answer_correct = not missing

    reasons = []
    if not retrieval_hit:
        reasons.append(
            f"expected {row['expected_source']!r} not retrieved (got {sorted(cited) or 'nothing'})"
        )
    if not answer_correct:
        reasons.append(f"answer missing {', '.join(repr(m) for m in missing)}")

    return {
        "passed": retrieval_hit and answer_correct,
        "retrieval_hit": retrieval_hit,
        "answer_correct": answer_correct,
        "reason": "; ".join(reasons) if reasons else "correct, expected source retrieved",
    }


def run_ragas(rows: list[dict], results: list[dict]) -> dict[int, dict[str, float]] | None:
    """Score answered rows with RAGAS's LLM-as-judge metrics.

    Returns {row index: {metric: score}}, or None if RAGAS isn't installed
    or nothing was answered. Judged by the app's own configured model and
    embeddings rather than RAGAS's defaults, so the scores describe the
    stack actually being shipped.

    Runs in two passes because the reference-based metrics need a
    ground-truth answer and `reference_answer` is optional: a row without
    one still gets faithfulness and answer relevancy rather than being
    dropped. Judge failures come back as NaN from ragas and are left that
    way - a bad row should show as a gap, not vanish into an average.
    """
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError:
        print("\nragas not installed - skipping LLM-judge metrics.")
        print("Install with: pip install -r requirements.txt")
        return None

    answered = [
        i for i, row in enumerate(rows) if not row["should_refuse"] and results[i]["grounded"]
    ]
    if not answered:
        print("\nNo answered (non-refused) rows to score with RAGAS.")
        return None
    with_reference = [i for i in answered if rows[i].get("reference_answer")]

    llm = LangchainLLMWrapper(rag_chain.get_llm())
    embeddings = LangchainEmbeddingsWrapper(vectorstore.get_embeddings())
    scores: dict[int, dict[str, float]] = {i: {} for i in answered}

    def score(indices, metrics, names):
        if not indices:
            return
        print(f"  {', '.join(names)} over {len(indices)} rows...")
        samples = [
            SingleTurnSample(
                user_input=rows[i]["question"],
                response=results[i]["answer"],
                retrieved_contexts=[s["text"] for s in results[i]["sources"]],
                reference=rows[i].get("reference_answer"),
            )
            for i in indices
        ]
        outcome = evaluate(
            EvaluationDataset(samples=samples),
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            raise_exceptions=False,
            show_progress=False,
        )
        for name in names:
            for position, i in enumerate(indices):
                scores[i][name] = outcome[name][position]

    print("\nScoring with RAGAS - this makes further judge calls per row...")
    score(answered, [Faithfulness(), AnswerRelevancy()], REFERENCE_FREE_METRICS)
    score(
        with_reference,
        [ContextPrecision(), ContextRecall(), AnswerCorrectness()],
        REFERENCE_BASED_METRICS,
    )
    return scores


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and v == v]  # v == v excludes NaN
    return sum(clean) / len(clean) if clean else None


def cell(value: bool | None) -> str:
    """Render a tri-state grading result for a markdown table cell."""
    return "—" if value is None else ("✅" if value else "❌")


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

    print()
    results, gradings = [], []
    for row in rows:
        result = rag_chain.answer_question(
            row["collection"], row["question"], persist_dir=PERSIST_DIR
        )
        grading = grade(row, result)
        results.append(result)
        gradings.append(grading)
        print(f"  {'PASS' if grading['passed'] else 'FAIL'}  {row['question'][:60]:62} {grading['reason']}")

    passes = sum(g["passed"] for g in gradings)
    summary = f"{passes}/{len(rows)} passed"
    print(f"\n{summary}")

    ragas_scores = run_ragas(rows, results)

    write_results(rows, results, gradings, summary, provider, model, collections, ragas_scores)
    print(f"\nWrote {RESULTS.relative_to(ROOT)}")
    return 0 if passes == len(rows) else 1


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


def write_results(rows, results, gradings, summary, provider, model, collections, ragas_scores) -> None:
    answerable = [i for i, r in enumerate(rows) if not r["should_refuse"]]
    refusal = [i for i, r in enumerate(rows) if r["should_refuse"]]
    retrieval_hits = [gradings[i]["retrieval_hit"] for i in answerable]
    answer_corrects = [gradings[i]["answer_correct"] for i in answerable]
    refusal_hits = [gradings[i]["passed"] for i in refusal]

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
        "| Signal | Score |",
        "|---|---|",
        f"| Retrieval-hit (expected file retrieved) | {sum(retrieval_hits)}/{len(retrieval_hits)} |",
        f"| Answer-correctness (expected facts present) | {sum(answer_corrects)}/{len(answer_corrects)} |",
        f"| Refusal accuracy (off-domain questions refused) | {sum(refusal_hits)}/{len(refusal_hits)} |",
    ]
    scores = ragas_scores or {}
    for metric in RAGAS_METRICS:
        values = [s[metric] for s in scores.values() if metric in s]
        avg = mean(values)
        avg_display = f"{avg:.2f}" if avg is not None else "n/a"
        lines.append(
            f"| RAGAS {metric.replace('_', ' ')} (n={len(values)}) | {avg_display} |"
        )

    lines += [
        "",
        f"Collections ingested from `data/`: {ingested}.",
        "",
        "Generated by `python eval/run_eval.py` — regenerate after changing the",
        "documents, the retrieval settings or the model. Answers come from the",
        "real LLM, so exact wording varies between runs.",
        "",
        "RAGAS scores are 0-1, judged by the same model and embeddings the app "
        "is configured with, not RAGAS's own defaults. `faithfulness` and "
        "`answer_relevancy` need no ground truth and cover every answered row; "
        "`context_precision`, `context_recall` and `answer_correctness` need "
        "the optional `reference_answer` in `eval_set.json` and cover only the "
        "rows that carry one. Refusal rows are skipped — there is no answer for "
        "a judge to read — and keep the refusal check instead. `—` means the "
        "metric does not apply to that row; `n/a` means the judge failed on it.",
        "",
        "> **Reading `answer_correctness`:** it is scored against a deliberately "
        "one-sentence `reference_answer`, so an answer that is correct *and "
        "adds further true detail from the documents* scores low — the extra "
        "claims have nothing in the reference to match. The lowest scores here "
        "are that, not wrong answers. Left as-is rather than padding the "
        "references until the number flatters: `faithfulness` is the metric "
        "that would actually catch an unsupported claim.",
        "",
        *caveats(collections),
        "| # | Collection | Question | Retrieval hit | Keywords | Refusal | "
        + " | ".join(m.replace("_", " ") for m in RAGAS_METRICS)
        + " | Sources |",
        "|---|---|---|---|---|---|" + "---|" * (len(RAGAS_METRICS) + 1),
    ]

    def score_cell(index: int, metric: str) -> str:
        value = scores.get(index, {}).get(metric)
        if value is None:
            return "—"
        return f"{value:.2f}" if value == value else "n/a"

    for i, row in enumerate(rows):
        grading = gradings[i]
        cited = ", ".join(
            sorted({f"{s['source']}#{s['chunk_index']}" for s in results[i]["sources"]})
        )
        detail = cited if grading["passed"] else f"**{grading['reason']}**"
        refusal_cell = "—" if not row["should_refuse"] else cell(grading["passed"])
        lines.append(
            f"| {i + 1} | `{row['collection']}` | {row['question']} "
            f"| {cell(grading['retrieval_hit'])} | {cell(grading['answer_correct'])} "
            f"| {refusal_cell} | "
            + " | ".join(score_cell(i, m) for m in RAGAS_METRICS)
            + f" | {detail} |"
        )
    lines.append("")
    RESULTS.write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
