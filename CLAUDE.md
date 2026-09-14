# Project instructions for Claude Code

This file is read automatically at the start of every session in this repo.

## Source of truth
SPEC.md is the specification. Build against it, not against this file or
any one-off prompt you're given — if a prompt and SPEC.md conflict,
SPEC.md wins (ask if it's genuinely ambiguous which one applies).

## The verify loop (harness + loop engineering)
`make verify` runs the automated portion of SPEC.md's Definition of Done:
tests, lint, a hardcoded-reference check, and a docker smoke test.

Discipline:
- Run `make verify` after every meaningful change, not just at the end.
- If it fails, read the actual failure, fix that, re-run. Don't guess blindly.
- If the SAME check fails 3 times in a row despite different fixes, stop
  looping on it — summarize what you've tried and what's blocking, and
  either ask me or move to a different piece of the spec. Unbounded retry
  on a stuck check wastes time and hides the real problem.
- Don't mark a requirement done until its mapped test (see SPEC.md's
  requirement-to-test table) passes under `make verify`.

## Git discipline
- Commit at the level of one requirement (or one clearly separable piece
  of a requirement), not one giant commit at the end.
- Message format: `<type>(<scope>): <what> [<FR/NFR ids>]`
  e.g. `feat(ingestion): chunk + embed pipeline [FR1, FR7]`
  `test(rag_chain): grounded answer + refusal cases [FR5, FR6]`
- Only commit once `make verify` is green for the piece you're committing —
  the commit history should double as a record of the verify loop, not a
  guess at what might work.
- Don't rewrite or squash history to make it look cleaner after the fact.
  An honest history that includes a fix commit is more credible than a
  falsified linear one.

## Testing discipline
- Write the test for a requirement alongside (not after) implementing it —
  SPEC.md's requirement-to-test mapping says which file each belongs in.
- Tests should be fast (SPEC.md NFR2: under 30s total) — mock the LLM call
  in unit tests rather than hitting a real API. The docker smoke test
  covers the real end-to-end path separately.

## Style
- Compact and readable over heavily abstracted — this is a timeboxed
  exercise, not a framework.
- `make lint` should be clean before a requirement is considered done.
