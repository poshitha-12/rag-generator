# Completion audit prompt

Run this now that the build looks complete. This is a full audit against
SPEC.md and CLAUDE.md, not a quick glance — go through every item below
and report evidence, not a verdict. "Looks fine" / "all done" is not an
acceptable answer anywhere in this audit; every line needs a test name,
a command's actual output, or a commit hash behind it.

---

Audit this repo against SPEC.md and CLAUDE.md. Report results as a
checklist — pass/fail plus evidence per item — not a paragraph summary.
Don't fix anything silently while auditing; surface every gap to me first,
including ones you could easily patch yourself.

## 1. Functional requirements — check FR1-FR8 individually
- FR1 — upload works for PDF/DOCX/TXT; no document is referenced by
  name/path/topic anywhere in `app/`
- FR2 — multiple named collections coexist independently
- FR3 — upload enqueues to Redis/RQ and returns immediately; UI shows a
  processing state until the job completes
- FR4 — collection selection + question flow works end to end
- FR5 — answers cite source file name + chunk index, grounded only in
  retrieved context
- FR6 — a genuinely out-of-context question gets an "I don't know"
  response, not a fabricated one
- FR7 — demonstrated with two actually-different document sets, zero code
  changes between them
- FR8 — chunk boundaries are paragraph/sentence-aware (per the separator
  priority in CLAUDE_CODE_PROMPT.md); show the test, and one real example
  chunk that would have split mid-sentence under a naive character cut
  but didn't

## 2. Non-functional requirements
- NFR1 — delete `chroma_store/`, then `docker compose up --build` from a
  clean checkout actually works
- NFR2 — `pytest -q` runtime is under 30 seconds (paste the actual timing)
- NFR3 — `make no-hardcoded` passes

## 3. Harness compliance
- Run `make verify` fresh and paste the actual output — not a summary of
  it. Confirm lint, tests, no-hardcoded, and docker-smoke all ran, none
  skipped.

## 4. Spec-driven development evidence
- Run `git log -- SPEC.md`. Was any requirement quietly weakened to match
  what got built, rather than the build meeting the original requirement?
  If something was descoped, it should say so explicitly in SPEC.md and
  to me — not be silently edited away.

## 5. Loop + git discipline evidence
- Paste `git log --oneline` in full.
- Is there evidence the verify loop actually ran — e.g. a fix commit after
  a failure — or does history read like everything worked first try?
  Either is fine; say honestly which it is.
- Do commit messages reference FR/NFR ids per CLAUDE.md's convention?

## 6. CI
- Is `.github/workflows/verify.yml` present, and if the repo's been
  pushed, is it passing? If it hasn't been pushed yet, say that rather
  than guessing at a status.

## 7. Documentation accuracy
- Does README.md's architecture diagram and setup instructions match what
  was actually built, including the queue and FR8's chunking approach?

## 8. Known gaps
- List anything in SPEC.md not fully satisfied, or simplified under time
  pressure, even if minor. Silence here is the exact failure mode this
  audit exists to catch — an omission is worse than an honestly flagged
  gap.