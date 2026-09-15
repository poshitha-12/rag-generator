# Post-audit fix prompt

Paste this into Claude Code. Covers the one real bug plus the cheap,
low-risk items from the completion audit. The items the audit flagged
that are NOT in this prompt (docker-smoke's container reuse, `make
verify` disrupting a running stack, FR3's manual refresh) are being
deliberately left alone — see the README task at the end, which
documents them instead of fixing them.

---

**1. Fix FR8 (the real finding).** In `app/ingestion.py`, the separator
priority list currently ranks a bare `\n` above sentence-ending
punctuation, so a hard-wrapped paragraph over the chunk size can split
mid-sentence at a line-wrap point instead of at a sentence boundary.
Reorder so paragraph breaks (`\n\n`) are first, sentence-ending
punctuation (`. `, `! `, `? `) come next, and bare `\n` ranks below
sentence punctuation (same tier as, or just above, a plain space) — not
above it.

Add a test fixture using a genuinely hard-wrapped paragraph (real
internal `\n` characters at a fixed width, over the chunk size, made of
short sentences so the last-resort exemption doesn't apply) — this is
the case the existing test suite didn't cover, so don't just re-test the
same `\n\n`-joined single-line style that already passed. Confirm no
chunk boundary from this fixture ends mid-sentence.

**2. CI: enforce NFR5.** Add `make no-heavy-deps` as a step in
`.github/workflows/verify.yml`, alongside the existing `make test` /
`make lint` / `make no-hardcoded` steps. This is the one NFR5-mapped
check currently missing from CI.

**3. Hygiene.**
- Add `.DS_Store` to `.gitignore` (and remove it from tracking if it's
  currently tracked: `git rm --cached .DS_Store data/.DS_Store` as
  needed).
- `EVAL_PROMPT.md` is untracked while the other prompt files
  (`CLAUDE_CODE_PROMPT.md`, `FINAL_REVIEW_PROMPT.md`, etc.) are tracked —
  add it for consistency.

**4. Document, don't fix.** Add a short "Known limitations" section to
README.md (near the trade-offs section) covering exactly these three
items, each in one or two honest sentences — don't implement fixes for
any of them right now:
- `make verify`'s docker-smoke check can validate an already-running
  container rather than a truly fresh one when the image is
  layer-identical to what's already up; NFR1 is independently confirmed
  via a real clean-clone test instead.
- Running `make verify` stops any currently-running dev stack
  (`docker-smoke` ends in `docker compose down`) — expected behavior
  given what it's for, but worth knowing before running it against a
  live demo session.
- FR3's processing state currently requires a manual "Refresh status"
  click rather than auto-polling; a real fix would need either a
  polling loop or a component like `streamlit-autorefresh`, both of
  which are a new moving part not worth introducing this late.

**After all of the above:** run `make verify`, confirm it's green
including the new `no-heavy-deps` CI step locally, commit (this can be
one commit or several — your call, but keep the FR8 fix as its own
commit given it's the substantive one: `fix(ingestion): rank sentence
boundaries above hard-wrap newlines [FR8]`), then `git push` so CI
actually runs against everything built since reranking — it currently
hasn't.
