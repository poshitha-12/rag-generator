# Refresh eval prompt

Re-run the eval harness — FR8's fix changed chunking for
02-leave-and-expenses.pdf, so eval/RESULTS.md was generated against
pre-fix chunking and no longer describes current HEAD.

---

Run `python eval/run_eval.py` again and let `eval/RESULTS.md` update with
whatever it actually produces this time — don't touch anything else.
Commit as `chore(eval): refresh RESULTS.md against post-FR8-fix
chunking`, then push.
