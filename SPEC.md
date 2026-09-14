# RAG Generator — Specification

Acceptance criteria the implementation must satisfy, written before any
code. This is the source of truth for "done" — the build is verified
against this spec, not against how it feels.

## Functional Requirements

- **FR1** — A user can upload one or more documents (PDF, DOCX, TXT)
  through the UI at runtime. No document is present in the codebase or
  referenced by name/path/topic anywhere in application code.
- **FR2** — Uploading a document set creates or appends to a named
  collection (user-provided or auto-generated). Multiple collections
  coexist independently.
- **FR3** — Uploading enqueues an ingestion job (chunk + embed) to a
  Redis-backed queue and returns immediately; the UI shows a processing
  state until the job completes.
- **FR4** — A user can select an existing collection and ask a
  natural-language question against it.
- **FR5** — Answers are grounded: retrieval returns top-k chunks, and the
  answer is generated only from those chunks, citing source file name +
  chunk index.
- **FR6** — If the retrieved context doesn't contain the answer, the
  system says it doesn't know rather than fabricating a response.
- **FR7** — Switching to a new, previously-unseen document domain requires
  zero code changes — only a new upload and a new collection name.
- **FR8** — Chunking is boundary-aware, not a raw character-count cut.
  Splits are made at paragraph breaks first; if a paragraph is larger than
  the target chunk size, at sentence boundaries (a `.`, `!`, or `?`
  followed by whitespace) next; a plain-space or raw-character split is
  used only as a last resort, when a single sentence itself exceeds the
  chunk size. No chunk should end mid-sentence except in that last-resort
  case.

## Non-Functional Requirements

- **NFR1** — `docker compose up --build` runs the full stack (app, redis,
  worker) from a clean checkout with no manual steps beyond an API key in
  `.env`.
- **NFR2** — Core logic (ingestion, retrieval) is covered by automated
  tests that run in under 30 seconds.
- **NFR3** — No hardcoded file paths, document names, or topic-specific
  strings exist in `app/`.

## Definition of Done

- [ ] All of FR1-FR8 manually verified with two unrelated document sets
- [ ] `pytest` passes
- [ ] `make no-hardcoded` passes (no sample-doc references leaked into `app/`)
- [ ] `docker compose up --build` succeeds from a clean clone
- [ ] README run instructions work verbatim on a machine that isn't yours

## Test-to-requirement mapping

| Requirement | Test |
|---|---|
| FR1, FR7 | `tests/test_ingestion.py::test_no_hardcoded_documents` |
| FR2 | `tests/test_vectorstore.py::test_collection_isolation` |
| FR3 | `tests/test_queue.py::test_upload_enqueues_job` |
| FR5, FR6 | `tests/test_rag_chain.py::test_grounded_answer_and_refusal` |
| FR8 | `tests/test_ingestion.py::test_chunk_boundaries_are_sentence_aware` |

Any requirement without a passing test isn't done, regardless of whether
the UI looks like it works.