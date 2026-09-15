# Prompts used, in order

Every prompt below was pasted into Claude Code as a distinct step, in this
order. Two files are deliberately not in the table: `CLAUDE.md` isn't a
prompt — it's persistent project instructions Claude Code loads
automatically every session, active throughout all seven steps below, not
run at any one point in the sequence. `SPEC.md` is the specification every
prompt below builds against or is checked against — also not a prompt
itself, but the thing all of them serve.

| # | File | What it did | Run when |
|---|---|---|---|
| 1 | `CLAUDE_CODE_PROMPT.md` | Initial build: ingestion, vector storage, queue, retrieval + generation, UI — implemented against SPEC.md, following CLAUDE.md's verify-loop and git discipline | First — this is the application build itself |
| 2 | `EVAL_PROMPT.md` | Built the first evaluation harness (retrieval-hit + keyword-match against real document content) | After the app worked end to end and a real LLM API key was in place |
| 3 | `RERANK_PROMPT.md` | Added cross-encoder reranking (FR9) and turned the refusal behavior into an explicit similarity-threshold gate (revised FR6) | After the initial eval baseline existed, so the effect of reranking could be measured |
| 4 | `RAGAS_PROMPT.md` | Replaced keyword-matching with real RAGAS metrics (faithfulness, answer relevancy, context precision/recall, answer correctness), wired to the real configured model instead of RAGAS's OpenAI default | Right after reranking landed, so the eval measures the actual shipped retrieval behavior |
| 5 | `FINAL_REVIEW_PROMPT.md` | The completion audit — walked every FR/NFR individually, demanding evidence (a test name, real output, a commit hash) rather than a verdict | Once every feature above was in place — found one real bug (FR8) plus six smaller gaps |
| 6 | `FIX_PROMPT.md` | Fixed the one real bug the audit found (FR8's hard-wrap handling), closed a CI gap (`no-heavy-deps` wasn't enforced) and two hygiene items, and documented — rather than fixed — three lower-risk items | Immediately after the audit |
| 7 | `REFRESH_EVAL_PROMPT.md` | Re-ran the eval harness, since the FR8 fix changed chunking for one document and the existing `RESULTS.md` predated that fix | Immediately after the FR8 fix — confirmed every aggregate score held steady |

**Not in this table, for reference:**
- `CLAUDE.md` — persistent instructions, active from step 1 onward
- `SPEC.md` — the living specification; amended incrementally across
  nearly every step above as new requirements (FR8, FR9, NFR4, NFR5) were
  added or clarified, and briefly diverged from the repo's actual state
  due to a file-sync gap corrected around commits `1e29ab9` / `841f1a2` /
  `8a8596d` — see those commits if that detail ever needs explaining.
