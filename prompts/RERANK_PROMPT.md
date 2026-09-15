# Reranking + similarity threshold prompt

Paste this into Claude Code. Builds FR6 (revised) and FR9 from SPEC.md.

---

Implement FR9 and the revised FR6 from SPEC.md:

**Reranking (FR9):** After initial retrieval, rerank the candidates with
`fastembed`'s `TextCrossEncoder` using the `Xenova/ms-marco-MiniLM-L-6-v2`
model specifically (small, ONNX, ~80MB — do NOT reach for
sentence-transformers, a bare `CrossEncoder`, or any other
PyTorch-backed reranker; `make no-heavy-deps` will fail the build if one
sneaks into requirements.txt, and it should). Retrieve a wider initial
candidate set (e.g. top 15-20 by vector similarity), rerank those, then
take the top-k by rerank score for the prompt.

**Similarity threshold refusal (revised FR6):** if the top reranked
candidate doesn't clear a threshold, skip the LLM call entirely and
return the fixed refusal string. Make the threshold a named constant in
`app/config.py`, not a magic number buried in `rag_chain.py`.

**Tests:**
- `tests/test_rag_chain.py::test_reranking_changes_chunk_order` — a case
  where vector similarity alone would rank a less-relevant chunk higher
  than a more-relevant one, and reranking corrects it. (If you can't
  construct a case where it visibly changes ordering, that's worth
  telling me rather than writing a test that doesn't actually exercise
  the reranker.)
- Update the existing refusal test to assert the threshold path is what
  fires (no LLM call made) for an off-domain question, not just that the
  refusal string comes back.

**After implementing:**
1. Run `make verify` — `no-heavy-deps` must pass alongside everything
   else.
2. Re-run `python eval/run_eval.py` and let `eval/RESULTS.md` update
   honestly — reranking can change which chunks get cited even for
   already-correct answers, and that's fine to show, not something to
   paper over.
3. Update SPEC.md's Definition of Done checkbox for FR9 and NFR5 only
   once genuinely verified, and commit as its own change:
   `feat(rag_chain): add fastembed reranking + similarity-threshold refusal [FR6, FR9, NFR5]`
