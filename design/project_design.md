# Rag_Micro — Hybrid RAG (Chroma + OpenSearch BM25)

This repo implements a microservice-based RAG system with:

- **Vector retrieval** in **Chroma**
- **Keyword/BM25 retrieval** in **OpenSearch** via a dedicated **search-service**
- **Hybrid retrieval (Pattern A)** in **query-service**: BM25 pre-filter → vector retrieval

---

## Services

### 1) ingestion-service

Responsibilities:

- Accept document uploads (`/ingest`)
- Parse file (PDF/text)
- Chunk text
- Generate embeddings
- Persist chunks to Chroma
- Index chunks to OpenSearch via search-service (`/index`)

Key dependencies:

- Embeddings endpoint (OpenAI-compatible via `BASE_URL`)
- Chroma
- search-service (BM25 indexing)

### 2) query-service

Responsibilities:

- Accept questions (`/query`)
- Embed query
- Retrieve relevant chunks (hybrid or vector-only)
- Build context
- Call LLM to generate answer
- Return answer + sources

Key dependencies:

- Embeddings endpoint
- LLM endpoint (OpenAI-compatible chat completions)
- Chroma
- search-service (BM25 query)

### 3) search-service

Responsibilities:

- Provide a simple BM25 API over OpenSearch
- Ensure OpenSearch index exists
- Index chunks (`/index`)
- Search BM25 (`/search`)
- Health check (`/health`)

Key dependencies:

- OpenSearch

### 4) OpenSearch

Responsibilities:

- Store searchable chunk text + metadata
- Provide BM25 ranking

### 5) Chroma

Responsibilities:

- Store embeddings + metadata + chunk text for vector similarity retrieval

---

## High-level Architecture (Design Flow)

Documents are ingested into **two stores**:

1. **OpenSearch** for BM25:

- fast keyword matching, exact terms, entities, names, IDs

2. **Chroma** for embeddings:

- semantic similarity, paraphrases, meaning-based matches

Hybrid retrieval combines both.

---

## User Flows

### A) Ingestion flow (`POST /ingest`) — “Put knowledge into the system”

1. Client uploads a file to `ingestion-service /ingest`
2. ingestion-service parses document → extracts text
3. Text is chunked (N chunks)
4. Each chunk is embedded via embeddings endpoint
5. Chunks + metadata persisted to Chroma (vector DB)
6. Each chunk is also indexed into OpenSearch through search-service `/index`
7. Response returns ingest status + counts

**Result**: the same knowledge is now available for both BM25 and vector search.

---

### B) Query flow (`POST /query`) — “Ask questions”

When `/query` is called with a question, query-service does:

1. Receive:

   - `question`
   - `top_k`
   - optional `model_name`
   - optional `document_id` filter

2. Embed the question (embedding model via `BASE_URL`)
3. Retrieve candidates:
   - If `document_id` was supplied: do **vector search only** within that doc (Chroma filter)
   - Else: do **Hybrid Pattern A**:
     1. Call BM25 search (`search-service /search`) with the question
     2. Use BM25 output to restrict vector retrieval to only candidates
     3. Query Chroma with a `where` filter (doc_ids) → return top_k chunks
4. Build LLM context from retrieved chunks
5. Call LLM (chat completions) with `{question + context}`
6. Return:
   - `answer`
   - `sources` (document_id, chunk_id, page, snippet)
   - `context_used`, `model_used`

---

## Hybrid Retrieval Strategy

### Current (Sprint 6): Pattern A (BM25 pre-filter → Chroma vector search)

- BM25 fetches candidates (currently oversampling, e.g. top_k\*3 or >=20)
- Candidate docs are selected from BM25 hits
- Vector search (Chroma) is restricted to those candidate docs
- LLM uses the returned chunk texts as context

> Note: Current implementation aggregates BM25 scores by document_id which can bias toward large docs that have many medium-scoring hits.

### Planned Next (Sprint 7): Industry-standard chunk-level hybrid

- Prefer chunk-level candidates (not doc aggregates)
- Expand context by including neighbors (prev/next chunks)
- Optional re-ranking:
  - embedding similarity re-rank, or cross-encoder re-ranker later

---

## Sprint-by-sprint Status

### Sprint 1 — Project skeleton + services baseline

✅ Implemented:

- Repo + service structure
- FastAPI apps run in Docker
- Health endpoints

---

### Sprint 2 — Ingestion pipeline (parse → chunk → embed → persist)

✅ Implemented:

- `POST /ingest` to upload files
- Chunking + embeddings (via OpenAI-compatible endpoint)
- Persist to Chroma

⚠️ Known issue:

- Chroma metadata values must be scalar types; lists/None can break ingestion

---

### Sprint 3 — Query pipeline (embed → retrieve → LLM answer)

✅ Implemented:

- `POST /query`
- Embed question
- Retrieve from Chroma
- Build context
- Generate answer using chat model
- Return sources + answer

---

### Sprint 4 — Debugging + retrieval diagnostics

✅ Implemented:

- Retrieval inspection scripts/logging
- Observed that some docs only appear far in top_k for pure vector queries

---

### Sprint 5 — Hybrid architecture planning

✅ Implemented:

- Selected Hybrid strategy: Pattern A first
- Added design direction toward OpenSearch BM25 + rerank

---

### Sprint 6 — Add OpenSearch + search-service + Pattern A integration

✅ Implemented:

- OpenSearch Docker container working
- search-service created:
  - `/health`
  - `/search` (BM25)
  - `/index` (index chunk)
- ingestion-service indexes into OpenSearch through search-service
- query-service integrated hybrid retrieval:
  - BM25 pre-filter → Chroma retrieval

⚠️ Known issues / limitations:

- ingestion metadata type safety (tags/None/list handling)
- hybrid selection is doc-aggregated → can bias toward large docs
- returned context can still be irrelevant → LLM may answer “I don’t know”

---

## Current State (End of Sprint 6)

✅ Working end-to-end:

- ingest → Chroma persist
- ingest → OpenSearch index
- BM25 search returns hits
- query-service can perform Hybrid Pattern A retrieval

⚠️ Needs improvement:

- metadata sanitation for Chroma
- hybrid retrieval must switch to chunk-level candidates + neighbor expansion
- optional rerank step for better final context quality

---

## Useful End-to-end Test Commands

### 1) Health checks

- ingestion-service: `GET /health`
- query-service: `GET /health` (if present)
- search-service: `GET http://localhost:8003/health`
- OpenSearch: `curl http://localhost:9200`

### 2) Ingest a PDF (example)

```bash
curl -v -X POST "http://localhost:8001/ingest" \
  -F "file=@/ABSOLUTE/PATH/YourDoc.pdf;type=application/pdf" \
  -F "document_id=your-doc-id"
```
