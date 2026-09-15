# Kickoff prompt for Claude Code (or Codex CLI)

Paste this after `cd`-ing into the repo. CLAUDE.md (persistent project
instructions — the verify loop, git commit convention, and testing
discipline all live there) and SPEC.md (the actual specification) already
exist and CLAUDE.md is loaded automatically — this prompt just kicks off
the work, it doesn't repeat what's already written down.

---

Implement this repo against SPEC.md, following the workflow in CLAUDE.md.
Work through the requirements roughly in order (FR1 → FR7), writing each
requirement's test alongside it, running `make verify`, and committing
once it's green for that piece — per CLAUDE.md's git discipline, not as
one commit at the end.

**Implementation guidance (not in SPEC.md — these are stack/style choices,
not requirements)**
- Stack: Streamlit UI, LangChain for orchestration, ChromaDB (persistent,
  local) for vector storage, sentence-transformers (all-MiniLM-L6-v2) for
  embeddings, Anthropic Claude by default / OpenAI as a fallback for
  generation (switchable via `LLM_PROVIDER` env var), RQ + Redis for the
  ingestion queue (packages and services are already in requirements.txt
  and docker-compose.yml).
- Chunking (FR8): use `RecursiveCharacterTextSplitter` with an explicit
  separator priority list — `["\n\n", "\n", ". ", "! ", "? ", " ", ""]` —
  so it prefers paragraph breaks, then sentence endings, and only falls
  back to a plain-space or character cut when a single sentence exceeds
  the chunk size. Target ~800 chars with ~100 overlap as a soft guide, not
  a hard cut point the boundary rules can't adjust.
- Retrieval: top-k similarity, k=4-6.
- Keep it compact: aim for a clean ~300-500 line app across app/main.py,
  app/ingestion.py, app/vectorstore.py, app/rag_chain.py, app/config.py.
  Prioritize working and readable over heavily abstracted.
- Populate /data with two small, clearly different sample document sets
  (e.g. a fictional company handbook and a product FAQ) so the app can be
  demoed switching domains without me sourcing my own files. (Yes, this
  means the `no-hardcoded` check in the Makefile greps for those exact
  names — that's intentional, it's there to catch you if the sample data
  leaks into app/ instead of staying in data/.)
- Don't touch docker-compose.lb.yml or nginx.conf — separate, optional
  load-balanced setup, out of scope for this pass.
- Update README.md only if something in the existing scaffold is wrong or
  incomplete — don't rewrite it wholesale.

Work end to end without stopping to ask me low-stakes implementation
questions — pick sensible defaults and note any assumptions in a short
comment block at the top of app/main.py. Do stop and ask if you hit a
genuine blocker (e.g. an API key is missing), or if the same `make verify`
check fails 3 times in a row (see CLAUDE.md).
