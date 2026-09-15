# Components

What each module in [`app/`](../app/) actually does, followed by one
worked example tracing a document from upload through to a cited answer.
See [ARCHITECTURE.md](ARCHITECTURE.md) for how these pieces fit together
and why the system is split this way.

## `config.py`

Everything env-driven, on purpose: no document names, paths, or topic
strings live here or anywhere in `app/` (NFR3) — every setting is a
knob, not a fact about a particular document set. Covers storage
locations (`CHROMA_PERSIST_DIR`, `REDIS_URL`), chunking (`CHUNK_SIZE`,
`CHUNK_OVERLAP`), retrieval (`TOP_K`, `RERANK_ENABLED`, `RERANK_FETCH_K`,
`SIMILARITY_THRESHOLD`), and generation (`LLM_PROVIDER` and the two
model names it switches between).

## `ingestion.py`

Turns raw uploaded bytes into embeddable, citable chunks.

- `load_document(filename, data)` — extracts plain text from PDF
  (`pypdf`), DOCX (`python-docx`), or TXT/MD bytes. Runs entirely in
  memory; nothing is written to a shared path, so the app and worker
  containers never need to agree on a filesystem.
- `chunk_text(text)` — boundary-aware splitting (FR8) via
  `RecursiveCharacterTextSplitter` with an explicit separator hierarchy:
  paragraph breaks (`\n\n`) first, then sentence terminators (`. `, `.\n`,
  `! `, `!\n`, `? `, `?\n`), then a bare `\n`, then a space, then a raw
  character cut as the last resort. The bare `\n` is deliberately ranked
  *below* sentence terminators — hard-wrapped source text usually breaks
  lines mid-sentence, so treating a lone newline as a preferred split
  point would cut mid-sentence exactly when FR8 says not to.
- `chunk_documents(documents)` — applies the above per file and attaches
  citation metadata (`source` filename, `chunk_index`) to every chunk.
- `ingest_documents(collection_name, documents)` — the unit of work the
  queue actually runs: chunk, then hand off to `vectorstore.add_chunks`.

## `vectorstore.py`

Owns ChromaDB collection lifecycle and the retrieval-quality pipeline.

- `normalize_collection_name(name)` — slugifies a user-typed name (or
  generates one) into something Chroma's naming rules accept.
- `get_embeddings()` / `get_reranker()` — lazily construct and cache the
  local ONNX models (FastEmbed embeddings, FastEmbed cross-encoder) once
  per process, so repeated calls don't reload them.
- `add_chunks(...)` — embeds and appends chunk records into a named,
  persistent collection, creating it if it doesn't exist yet (FR2).
- `similarity_search(collection_name, query, k)` — the retrieval
  pipeline, three steps:
  1. Pull `RERANK_FETCH_K` candidates by plain vector similarity (wider
     than `k`, so reranking has a real shortlist to work with).
  2. Re-score every candidate with the cross-encoder, which reads the
     query and chunk text together rather than comparing embedding
     vectors — a more accurate but more expensive signal, which is why
     it only runs on the shortlist (FR9).
  3. If the best reranked score is still below `SIMILARITY_THRESHOLD`,
     return nothing — the gate behind FR6's refusal. This is a plain
     number comparison, not a model decision, which is why it's the
     primary defense rather than the prompt instruction in
     `rag_chain.py`.

## `jobs.py`

The Redis/RQ ingestion queue (FR3). `enqueue_ingestion` hands
`ingestion.ingest_documents` to a worker process and returns a job id
immediately; `job_state` reports `queued` / `started` / `finished` /
`failed` back to the UI. Deliberately thin — all the actual ingestion
logic lives in `ingestion.py` so it's callable (and testable) without a
queue in the loop.

## `rag_chain.py`

Retrieval + grounded generation (FR4, FR5, FR6).

- `PROMPT` — a system message that instructs the model to answer only
  from the given context, refuse with an exact fixed string when it
  can't, and cite `[source: <file>, chunk <index>]` inline. This is the
  *second* line of defense for FR6 — the threshold gate in
  `vectorstore.py` is the first and does most of the work.
- `get_llm()` — constructs the chat model lazily (only when a question is
  actually asked), switched between Anthropic and OpenAI by
  `config.LLM_PROVIDER`. Lazy construction means the app boots and lets
  you browse/upload even without an API key set.
- `answer_question(collection_name, question, k)` — the entry point the
  UI calls: retrieve (possibly refusing immediately, no LLM call spent),
  format context with citation labels, invoke the LLM, and return
  `{answer, sources, grounded}`.

## `main.py`

The Streamlit UI — no business logic of its own, just wiring:

- **Upload sidebar** — file uploader, a collection-name text input,
  enqueues ingestion via `jobs.enqueue_ingestion`, and lists per-job
  status polled from `jobs.job_state` (a manual "Refresh status" button
  advances it — see the README's Known Limitations for why this isn't
  automatic yet).
- **Query pane** — a collection picker (`vectorstore.list_collections`),
  a chat input, and a chat history rendered per collection. Each turn
  calls `rag_chain.answer_question` and renders the answer plus an
  expandable list of cited source chunks.

## Worked example: one question, end to end

Say two collections already exist — `company-handbook` and
`product-faq` — and the user picks `company-handbook` and asks
*"How many vacation days do new hires get?"*

1. **UI** (`main.py`) reads the selected collection and the question
   text, calls `rag_chain.answer_question("company-handbook", "How many
   vacation days do new hires get?", k=5)`.
2. **Retrieval** (`vectorstore.similarity_search`) embeds the question
   with FastEmbed, pulls `RERANK_FETCH_K=20` candidate chunks from the
   `company-handbook` Chroma collection by vector distance.
3. **Rerank** — the cross-encoder scores each of the 20 candidates
   against the literal question text. Say the top-scoring chunk is
   `02-leave-and-expenses.pdf`, chunk 3, at a score of `+2.1`.
4. **Gate** — `2.1 >= SIMILARITY_THRESHOLD (-8.0)`, so the gate passes;
   the top 5 reranked chunks are returned.
5. **Prompt build** (`rag_chain.format_context`) renders those 5 chunks
   as `[source: 02-leave-and-expenses.pdf, chunk 3]\n<text>` blocks,
   concatenated, and fills the prompt template with that context plus
   the question.
6. **Generation** — `get_llm()` builds a `ChatAnthropic` (or
   `ChatOpenAI`, depending on `LLM_PROVIDER`) client and invokes it. The
   model answers strictly from the passed chunks, e.g. *"New hires
   accrue 15 vacation days in their first year [source:
   02-leave-and-expenses.pdf, chunk 3]."*
7. **Response shaping** — since the answer doesn't start with the fixed
   refusal string, `answer_question` marks it `grounded: true` and
   attaches the 5 source chunks as `sources`.
8. **UI** renders the answer as a chat bubble and the 5 sources in an
   expandable "Sources" panel underneath it.

Now say the same collection is asked *"What's the capital of France?"*
— an off-domain question. Step 3's cross-encoder can't find anything in
the handbook that's actually about capitals or France, so every
candidate scores far below the threshold (say the best is `-11.2`). Step
4's gate fails: `similarity_search` returns `[]` before any reranked
context reaches a prompt. `answer_question` short-circuits at that point
— no LLM call is made at all — and returns the fixed `NO_ANSWER` string
with `sources: []`, `grounded: false`. The UI renders that as the
assistant's reply, with no sources panel (there's nothing to cite).

Switching to `product-faq` and asking a product question repeats exactly
this flow against a different collection — nothing in `app/` changes,
which is FR7 in practice rather than just in the spec.
