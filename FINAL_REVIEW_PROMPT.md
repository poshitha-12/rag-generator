# Final review prompt

Run this after the main build looks done — it's a deliberate second pass,
not a formality.

---

Before declaring this finished:

1. Run `make verify` one more time from a clean state and confirm it's
   green.
2. Walk through SPEC.md's Definition of Done checklist item by item and
   tell me, for each one, whether it's satisfied and how you know (which
   test, which manual check) — don't just say "done."
3. Look at `git log --oneline`. Is it a legible record of the build (one
   logical change per commit, clear messages), or did some steps get
   lumped together? If it's lumped, leave it as-is (don't rewrite history
   now), but tell me honestly rather than claiming it's clean if it isn't.
4. Confirm README.md's run instructions are still accurate for what you
   actually built.
5. List anything in SPEC.md you deliberately deferred or simplified due to
   time, so I can decide whether to call it out as a known trade-off
   rather than have it discovered later.

Don't fix anything silently in this pass except trivial README
corrections — surface everything else to me first.
