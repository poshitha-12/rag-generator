# Evaluation harness prompt

Run this once your real LLM API key is in `.env` — this needs to call
the actual model, not a stand-in, or the results mean nothing.

---

Build NFR4 from SPEC.md: a small evaluation harness that measures answer
*quality*, separate from the pytest suite (which checks that the grounding
mechanism is enforced, not that answers are actually correct).

1. **`eval/eval_set.json`** — read the real sample files in `data/` and
   write genuine questions against their actual content (don't invent
   facts that aren't in the documents). At least 4 answerable questions
   per document set, plus at least 1 deliberately off-domain question per
   set to check refusal. Each entry:
   ```json
   {
     "collection": "handbook",
     "question": "...",
     "expected_answer_keywords": ["...", "..."],
     "should_refuse": false
   }
   ```
   For `should_refuse: true` entries, omit `expected_answer_keywords`.

2. **`eval/run_eval.py`** — a standalone script (not wired into
   `make verify`, since it needs a real API key and spends real tokens):
   - Ingests each collection's source file(s) from `data/` directly via
     the existing ingestion/vectorstore functions (call them synchronously
     here — skip the Redis queue, this doesn't need it).
   - For each question, runs it through the real `rag_chain` query path.
   - Non-refusal rows: pass if the answer contains all
     `expected_answer_keywords` (case-insensitive substring) AND the cited
     source matches the question's collection.
   - `should_refuse` rows: pass if the response matches the refusal
     behavior already established in `rag_chain` (reuse that logic/check,
     don't reinvent a second definition of "refused").
   - Prints a summary line (e.g. `7/8 passed`) and writes `eval/RESULTS.md`
     as a markdown table: question, collection, expected, pass/fail.

3. **Makefile** — add an `eval` target that just runs
   `python eval/run_eval.py`. Do NOT add it to the `verify` target — it
   needs a live key and costs tokens, `make verify` should stay free and
   key-independent.

4. **README.md** — add a short "Evaluation" section linking to
   `eval/RESULTS.md`, one paragraph explaining it measures answer quality
   against real content, separately from the correctness tests. Add one
   line to the trade-offs section noting that a framework like RAGAS
   (faithfulness/context-precision/context-recall scoring via an
   LLM judge) is the natural next step with more time — this hand-written
   set is deliberately small and manual by comparison.

Commit as its own change once `python eval/run_eval.py` actually runs and
`eval/RESULTS.md` looks sane — don't commit a fabricated-looking 100%
pass rate without actually running it; if something genuinely fails,
that's useful information, report it honestly rather than adjusting the
eval set until it passes.
