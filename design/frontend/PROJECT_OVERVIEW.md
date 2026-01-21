# RAG Micro - Complete Project Overview

## 🎯 Project Purpose

This is a **Hybrid RAG (Retrieval-Augmented Generation)** microservices system that combines:
- **BM25 keyword search** (via OpenSearch) for exact term matching
- **Vector similarity search** (via Chroma) for semantic understanding
- **LLM generation** (via OpenAI-compatible API) for answering questions

The system ingests documents (PDFs), chunks them, indexes them in both stores, and then uses a hybrid retrieval strategy to answer user questions with citations.

---

## 🏗️ Architecture Overview

### Services (4 microservices + 2 data stores)

1. **ingestion-service** (Port 8001)
   - Accepts document uploads
   - Parses PDFs, chunks text, generates embeddings
   - Stores in Chroma (vector DB) and OpenSearch (BM25 index)

2. **query-service** (Port 8002)
   - Accepts user questions
   - Performs hybrid retrieval (BM25 → Vector → Neighbors)
   - Generates answers using LLM
   - Returns answer + source citations

3. **search-service** (Port 8003)
   - BM25 search API wrapper over OpenSearch
   - Handles indexing and searching of text chunks

4. **opensearch** (Port 9200)
   - Elasticsearch-compatible search engine
   - Stores chunk text for BM25 keyword matching

5. **Chroma** (Persistent volume)
   - Vector database for embeddings
   - Stores chunk text + metadata + embeddings

6. **Model Providers** (via docker-model-runner)
   - Embeddings model: `qwen3-embedding:8B-Q4_K_M`
   - LLM chat model: `qwen3`

---

## 📊 Data Flow

### Ingestion Flow (`POST /ingest`)

```
User uploads PDF
    ↓
ingestion-service receives file
    ↓
DocumentLoader.load_pages() → Extract text per page
    ↓
fixed_chunk_text() → Split into overlapping chunks (500 chars, 50 overlap)
    ↓
embed_texts() → Generate embeddings via OpenAI-compatible API
    ↓
persist_chunks() → 
    ├─→ Chroma: Store embeddings + metadata + chunk text
    └─→ search-service/index → OpenSearch: Store chunk text for BM25
    ↓
Return: {status, document_id, chunks, characters, embedding_dim}
```

**Key Files:**
- `ingestion_service/app/api/ingest.py` - Main API endpoint
- `ingestion_service/app/processing/loader.py` - PDF parsing
- `ingestion_service/app/processing/chunker.py` - Text chunking
- `ingestion_service/app/processing/embeddings.py` - Embedding generation
- `ingestion_service/app/processing/persist.py` - Dual storage (Chroma + OpenSearch)

**Chunk ID Format:** `{document_id}::{chunk_id}` (e.g., `"cover latter::0"`)

**Metadata Stored:**
- `document_id`: Logical document identifier
- `chunk_id`: Numeric chunk index within document
- `source`: Original filename
- `page`: Page number (1-based)
- `tags`: Optional tags (comma-separated in Chroma, list in OpenSearch)

---

### Query Flow (`POST /query`)

```
User sends question
    ↓
query-service receives {question, top_k, model_name?, document_id?}
    ↓
embed_query() → Generate embedding for question
    ↓
retrieve_context() → Hybrid retrieval:
    ├─ If document_id provided:
    │   └─→ Pure vector search in Chroma (filtered by document_id)
    │
    └─ Else (Hybrid Pattern A):
        ├─→ search_bm25() → Get top N chunk candidates from OpenSearch
        ├─→ Fetch center chunks from Chroma by deterministic IDs
        ├─→ Fuse scores: normalized_cosine * alpha + normalized_bm25 * (1-alpha)
        ├─→ Select top centers (relative threshold + hard-keep BM25 #1)
        ├─→ fetch_with_neighbors() → Expand each center with ±window chunks
        └─→ Dedupe and rank by evidence_score
    ↓
build_context() → Combine chunks into context string (max 12000 chars)
    ↓
generate_answer() → Call LLM with context + question
    ↓
build_sources() → Extract and rank source citations
    ↓
Return: {answer, sources[], context_used, model_used}
```

**Key Files:**
- `query_service/app/api/query.py` - Main query logic (400+ lines, complex hybrid retrieval)
- `query_service/app/services/bm25_client.py` - BM25 search client
- `query_service/app/services/neighbors.py` - Neighbor expansion logic
- `query_service/app/services/llm.py` - LLM answer generation

**Hybrid Retrieval Config (Environment Variables):**
- `HYBRID_BM25_CHUNKS` (default: 50) - How many BM25 candidates to fetch
- `HYBRID_CENTER_K` (default: 3) - How many centers to select
- `HYBRID_NEIGHBOR_WINDOW` (default: 2) - Chunks before/after center to include
- `HYBRID_MAX_CONTEXT_CHUNKS` (default: 30) - Max chunks in final context
- `HYBRID_FUSION_ALPHA` (default: 0.6) - Weight for cosine similarity (0.6 = 60% vector, 40% BM25)
- `HYBRID_CENTER_REL_THRESHOLD` (default: 0.85) - Relative score threshold for centers
- `HYBRID_DISTANCE_PENALTY` (default: 0.02) - Penalty per chunk distance from center

**Source Citation Format:**
```json
{
  "document_id": "cover latter",
  "chunk_id": "0",
  "source": "Cover Latter.pdf",
  "page": 1,
  "snippet": "First 200 chars of chunk text..."
}
```

---

## 🔧 API Endpoints

### Ingestion Service (Port 8001)

**POST `/ingest`**
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `file`: UploadFile (PDF or text)
  - `document_id`: str (optional, defaults to filename stem)
  - `source`: str (optional, defaults to filename)
  - `version`: str (optional)
- **Response:**
```json
{
  "status": "embedded",
  "document_id": "cover latter",
  "characters": 5432,
  "chunks": 12,
  "embedding_dim": 4096,
  "preview": "First 200 chars..."
}
```

**GET `/health`**
- Returns service status

---

### Query Service (Port 8002)

**POST `/query`**
- **Content-Type:** `application/json`
- **Request Body:**
```json
{
  "question": "how much experience does ali haider has?",
  "top_k": 5,
  "model_name": "ai/qwen3:latest",  // optional
  "document_id": "cover latter"     // optional, restricts search
}
```
- **Response:**
```json
{
  "answer": "Ali Haider has over four years of experience...",
  "sources": [
    {
      "document_id": "cover latter",
      "chunk_id": "0",
      "source": "Cover Latter.pdf",
      "page": 1,
      "snippet": "I have over four years of experience..."
    }
  ],
  "context_used": 3456,
  "model_used": "ai/qwen3:latest"
}
```

**GET `/health`**
- Returns service status

---

### Search Service (Port 8003)

**POST `/index`**
- **Content-Type:** `application/json`
- **Request Body:**
```json
{
  "document_id": "cover latter",
  "chunk_id": 0,
  "source": "Cover Latter.pdf",
  "page": 1,
  "text": "Chunk text content...",
  "tags": ["resume", "cover-letter"]  // optional
}
```
- **Response:**
```json
{
  "index": "docs_bm25",
  "id": "auto-generated-id",
  "result": "created"
}
```

**POST `/search`**
- **Content-Type:** `application/json`
- **Request Body:**
```json
{
  "query": "how much experience",
  "top_k": 10,
  "document_ids": ["cover latter"],  // optional filter
  "sources": ["Cover Latter.pdf"]   // optional filter
}
```
- **Response:**
```json
{
  "hits": [
    {
      "document_id": "cover latter",
      "chunk_id": 0,
      "source": "Cover Latter.pdf",
      "page": 1,
      "text": "Chunk text...",
      "tags": [],
      "score": 8.234
    }
  ],
  "total": 1
}
```

**GET `/health`**
- Returns service status + OpenSearch connection info

---

## 🗄️ Data Storage

### Chroma (Vector Database)

**Location:** Persistent volume at `/chroma_data` (shared between ingestion and query services)

**Collection:** `documents` (configurable via `CHROMA_COLLECTION` env var)

**Schema:**
- **ID:** `{document_id}::{chunk_id}` (deterministic, allows neighbor fetching)
- **Document:** Full chunk text
- **Embedding:** Vector (dimension from embedding model, e.g., 4096)
- **Metadata:**
  - `document_id`: str
  - `chunk_id`: int (numeric for neighbor math)
  - `source`: str (filename)
  - `page`: int
  - `tags`: str (comma-separated, optional)

**Similarity:** Cosine similarity (`hnsw:space: cosine`)

---

### OpenSearch (BM25 Index)

**Index Name:** `docs_bm25` (configurable via `OPENSEARCH_INDEX` env var)

**Mapping:**
```json
{
  "document_id": "keyword",
  "chunk_id": "integer",
  "source": "keyword",
  "page": "integer",
  "text": "text",  // BM25 searchable
  "tags": "keyword"
}
```

**Search:** BM25 algorithm (default OpenSearch similarity)

---

## 🔐 Environment Variables

### Required (All Services)

- `BASE_URL`: OpenAI-compatible API base URL
- `OPENAI_API_KEY`: API key (can be dummy if auth not required)
- `MODEL_EMBED`: Embedding model identifier (e.g., `qwen3-embedding:8B-Q4_K_M`)
- `MODEL_CHAT`: LLM model identifier (e.g., `ai/qwen3:latest`)

### Ingestion Service

- `CHROMA_PERSIST_DIR`: Chroma data directory (default: `/chroma_data`)
- `CHROMA_COLLECTION`: Collection name (default: `documents`)
- `SEARCH_SERVICE_URL`: URL to search-service (default: `http://search-service:8003`)

### Query Service

- `CHROMA_PERSIST_DIR`: Chroma data directory (default: `/chroma_data`)
- `CHROMA_COLLECTION`: Collection name (default: `documents`)
- `SEARCH_SERVICE_URL`: URL to search-service (default: `http://search-service:8003`)
- `HYBRID_BM25_CHUNKS`: BM25 candidate count (default: 50)
- `HYBRID_CENTER_K`: Number of centers (default: 3)
- `HYBRID_NEIGHBOR_WINDOW`: Neighbor window size (default: 2)
- `HYBRID_MAX_CONTEXT_CHUNKS`: Max context chunks (default: 30)
- `HYBRID_FUSION_ALPHA`: Fusion weight (default: 0.6)
- `HYBRID_CENTER_REL_THRESHOLD`: Center threshold (default: 0.85)
- `HYBRID_DISTANCE_PENALTY`: Distance penalty (default: 0.02)

### Search Service

- `OPENSEARCH_HOST`: OpenSearch host (default: `opensearch`)
- `OPENSEARCH_PORT`: OpenSearch port (default: `9200`)
- `OPENSEARCH_SCHEME`: `http` or `https` (default: `http`)
- `OPENSEARCH_USER`: Username (default: `admin`)
- `OPENSEARCH_PASSWORD`: Password (default: `Admin123!`)
- `OPENSEARCH_INDEX`: Index name (default: `docs_bm25`)

---

## 🐳 Docker Compose Setup

**Services:**
- `ingestion-service`: Port 8001
- `query-service`: Port 8002
- `search-service`: Port 8003
- `opensearch`: Port 9200
- `docker-model-runner`: Embeddings provider
- `llm`: LLM provider

**Volumes:**
- `chroma_data`: Shared between ingestion and query services
- `opensearch_data`: OpenSearch persistence

**Networking:**
- All services on default Docker network
- Services communicate via service names (e.g., `http://search-service:8003`)

---

## 🎨 Frontend Integration Points

### For Document Upload UI:

1. **Upload Form:**
   - File input (PDF)
   - Optional: document_id input
   - Optional: source name input
   - Submit to `POST http://localhost:8001/ingest` (multipart/form-data)

2. **Upload Progress:**
   - Show response: `{status, document_id, chunks, characters}`
   - Display success/error messages

3. **Document List:**
   - Track uploaded `document_id`s
   - Could query Chroma/OpenSearch to list all documents (not implemented yet)

---

### For Query/Question UI:

1. **Question Input:**
   - Text area for question
   - Optional: document_id dropdown (filter to specific document)
   - Optional: top_k slider (1-20)
   - Submit to `POST http://localhost:8002/query`

2. **Answer Display:**
   - Show `answer` text
   - Display `sources` as citations with:
     - Document name (`source`)
     - Page number
     - Snippet preview
     - Link to full chunk (if implemented)

3. **Loading States:**
   - Embedding generation
   - BM25 search
   - Vector retrieval
   - LLM generation

4. **Error Handling:**
   - Network errors
   - Service unavailable
   - Empty results

---

### For Search Service (Optional Admin UI):

1. **BM25 Search:**
   - Direct BM25 search interface
   - Show hits with scores
   - Useful for debugging retrieval

2. **Index Status:**
   - Health check: `GET http://localhost:8003/health`
   - Show OpenSearch cluster info

---

## 🔍 Key Implementation Details

### Chunking Strategy

- **Method:** Fixed-size overlapping chunks
- **Size:** 500 characters (whitespace-tokenized)
- **Overlap:** 50 characters
- **Per-page:** Chunks are created per page, preserving page numbers

### Hybrid Retrieval Strategy (Pattern A)

1. **BM25 Pre-filter:** Get top N chunk candidates (oversample, e.g., 50)
2. **Center Selection:** Fetch those chunks from Chroma, compute cosine similarity, fuse with BM25 scores
3. **Neighbor Expansion:** For each selected center, fetch ±window chunks (default ±2)
4. **Deduplication:** Remove duplicate (document_id, chunk_id) pairs
5. **Ranking:** Sort by `evidence_score = center_score - (distance * penalty)`
6. **Context Building:** Combine top chunks into context string (max 12000 chars)

### LLM Prompt Template

```
System: "You are a helpful assistant. Answer using ONLY the provided context. 
         If the context is insufficient, say you don't know."

User: "CONTEXT:
       [Chunk 1]
       {chunk_text_1}
       
       [Chunk 2]
       {chunk_text_2}
       ...
       
       QUESTION:
       {user_question}
       
       INSTRUCTIONS:
       - Use the context only
       - Be concise
       - If not found in context, say: 'I don't know based on the provided document(s).'"
```

---

## 🚨 Known Issues / Limitations

1. **Metadata Type Safety:**
   - Chroma requires scalar metadata values (no lists/None)
   - Tags are stored as comma-separated strings in Chroma, but lists in OpenSearch

2. **Hybrid Selection Bias:**
   - Current doc-aggregation can bias toward large documents with many medium-scoring hits
   - Future: Chunk-level candidates (partially implemented)

3. **Context Quality:**
   - Retrieved context can still be irrelevant → LLM may answer "I don't know"
   - Future: Re-ranking with cross-encoder

4. **Error Handling:**
   - BM25 indexing failures are logged but don't block Chroma ingestion
   - If OpenSearch is down, ingestion continues (Chroma only)

---

## 📝 Testing

See `design/testing.md` for comprehensive end-to-end testing checklist.

**Quick Test Commands:**

```bash
# Health checks
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Ingest document
curl -X POST "http://localhost:8001/ingest" \
  -F "file=@document.pdf" \
  -F "document_id=my-doc"

# Query
curl -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is this about?","top_k":5}'
```

---

## 🎯 Next Steps for Frontend

1. **Create React/Vue/Next.js app** with:
   - Document upload page
   - Query/chat interface
   - Source citation display

2. **API Integration:**
   - Use `fetch` or `axios` to call service endpoints
   - Handle multipart uploads for ingestion
   - Display streaming responses (if LLM supports streaming)

3. **State Management:**
   - Track uploaded documents
   - Store query history
   - Cache recent answers

4. **UI Components:**
   - File upload with drag-and-drop
   - Chat interface for questions
   - Citation cards with expandable snippets
   - Loading indicators for async operations

5. **Error Handling:**
   - Network error messages
   - Service unavailable fallbacks
   - Validation errors (file type, question length)

---

## 📚 File Structure Summary

```
Rag_Micro/
├── docker-compose.yml          # Service orchestration
├── ingestion_service/
│   ├── app/
│   │   ├── main.py             # FastAPI app
│   │   ├── api/ingest.py       # POST /ingest endpoint
│   │   ├── processing/         # Chunking, embedding, persistence
│   │   ├── db/chroma.py        # Chroma client
│   │   └── services/bm25_indexer.py  # OpenSearch indexing
│   └── Dockerfile
├── query_service/
│   ├── app/
│   │   ├── main.py             # FastAPI app with logging
│   │   ├── api/query.py        # POST /query endpoint (complex hybrid logic)
│   │   ├── services/
│   │   │   ├── bm25_client.py  # BM25 search client
│   │   │   ├── neighbors.py   # Neighbor expansion
│   │   │   └── llm.py          # LLM answer generation
│   │   └── schemas/query.py    # Pydantic models
│   └── Dockerfile
├── search_service/
│   ├── app/
│   │   ├── main.py             # FastAPI app
│   │   ├── index.py            # OpenSearch client + index creation
│   │   ├── schemas.py          # Pydantic models
│   │   └── config.py           # OpenSearch settings
│   └── Dockerfile
└── design/                      # Architecture documentation
```

---

This project is a production-ready hybrid RAG system with sophisticated retrieval, neighbor expansion, and citation tracking. The frontend will primarily interact with the ingestion and query services, providing a user-friendly interface for document management and question-answering.

