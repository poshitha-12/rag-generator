# RAGAS integration prompt

Paste this into Claude Code. This upgrades NFR4's eval harness from the
hand-rolled keyword-match version to real RAGAS metrics.

RAGAS's API has changed across versions — don't assume a specific import
path from memory. After installing, check the actually-installed
version (`pip show ragas`) and its real API (its own docs/changelog, or
introspect the installed package) before writing integration code
against it.

---

Upgrade the evaluation harness (NFR4 in SPEC.md) to use RAGAS instead of
keyword matching.

**Install:** add `ragas` to requirements.txt with NO extras (no
`ragas[all]` or similar — see NFR5). After installing, run
`pip list | grep -iE "torch|tensorflow"`. If either shows up, STOP and
tell me before doing anything else — don't let a docker rebuild balloon
again. Only proceed once that check is clean. Pin the exact version that
actually resolved into requirements.txt for reproducibility.

**Wire it to the real stack, not RAGAS's defaults:**
- LLM judge: wrap the same `ChatAnthropic` instance already used for
  generation (via requirements.txt's `langchain-anthropic`) in RAGAS's
  LangChain LLM wrapper, so metrics are judged by the model you're
  actually shipping, not GPT.
- Embeddings: wrap the existing `FastEmbedEmbeddings` instance the same
  way, for any metric that needs embeddings.

**eval_set.json:** add an optional `reference_answer` field — a genuine,
one-sentence answer drawn from the actual document content (same
no-fabrication discipline as before). Don't invent one for every row if
it doesn't fit naturally; it's fine for some rows to only get the
reference-free metrics.

**Metrics to compute:**
- Faithfulness + answer relevancy — every answerable (non-refusal) row,
  these don't need a reference answer.
- Context precision + context recall + answer correctness — only rows
  that have a `reference_answer`.
- `should_refuse` rows: skip RAGAS scoring entirely (there's no
  meaningful "context" being used) — keep the existing refusal-check
  logic for those, don't replace something that already works.

**Output:** `eval/RESULTS.md` as a table — question, collection, each
applicable metric's score (0-1), and the existing refusal pass/fail for
refusal rows. Report real numbers, including any that come back lower
than you'd like; a metric that's honestly 0.6 is more useful than one
quietly excluded because it wasn't flattering.

**Cleanup:** the README trade-offs line that said "RAGAS would be the
next step with more time" is now stale — remove or update it, since this
is that step.

**Before committing:** run `make verify` (unaffected — this isn't wired
into it) and confirm `python eval/run_eval.py` actually runs against the
real API key and produces real scores, not placeholders. Commit as its
own change: `feat(eval): replace keyword-match harness with RAGAS metrics [NFR4]`.

This will spend real tokens (every question now gets extra judge calls
on top of the generation call) and take longer than the previous
version — that's expected, not a bug.
