# API Reference for Frontend Integration

Quick reference for frontend developers integrating with the RAG Micro services.

---

## Base URLs

- **Ingestion Service:** `http://localhost:8001`
- **Query Service:** `http://localhost:8002`
- **Search Service:** `http://localhost:8003`

---

## 1. Document Ingestion

### `POST /ingest`

Upload a document (PDF or text) to be indexed.

**Endpoint:** `http://localhost:8001/ingest`

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `file` (required): File upload (PDF or `.txt`)
- `document_id` (optional): Custom document identifier (defaults to filename without extension)
- `source` (optional): Source name/label (defaults to filename)
- `version` (optional): Version string

**Example (JavaScript/Fetch):**
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('document_id', 'my-document');
formData.append('source', 'My Document.pdf');

const response = await fetch('http://localhost:8001/ingest', {
  method: 'POST',
  body: formData
});

const result = await response.json();
// {
//   "status": "embedded",
//   "document_id": "my-document",
//   "characters": 5432,
//   "chunks": 12,
//   "embedding_dim": 4096,
//   "preview": "First 200 chars..."
// }
```

**Example (cURL):**
```bash
curl -X POST "http://localhost:8001/ingest" \
  -F "file=@document.pdf" \
  -F "document_id=my-document" \
  -F "source=My Document.pdf"
```

**Success Response (200):**
```json
{
  "status": "embedded",
  "document_id": "my-document",
  "characters": 5432,
  "chunks": 12,
  "embedding_dim": 4096,
  "preview": "First 200 characters of first chunk..."
}
```

**Error Responses:**
- `400`: Invalid file type, empty document, or validation error
- `500`: Server error (embedding failure, storage error)

---

## 2. Query / Question Answering

### `POST /query`

Ask a question and get an answer with source citations.

**Endpoint:** `http://localhost:8002/query`

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "question": "What is this document about?",
  "top_k": 5,
  "model_name": "ai/qwen3:latest",  // optional
  "document_id": "my-document"      // optional, restricts to specific document
}
```

**Fields:**
- `question` (required, min 3 chars): User's question
- `top_k` (optional, default 5, range 1-20): Number of chunks to retrieve
- `model_name` (optional): LLM model to use (defaults to `MODEL_CHAT` env var)
- `document_id` (optional): Filter search to specific document

**Example (JavaScript/Fetch):**
```javascript
const response = await fetch('http://localhost:8002/query', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    question: 'What is this document about?',
    top_k: 5,
    document_id: 'my-document'  // optional
  })
});

const result = await response.json();
// {
//   "answer": "This document is about...",
//   "sources": [...],
//   "context_used": 3456,
//   "model_used": "ai/qwen3:latest"
// }
```

**Success Response (200):**
```json
{
  "answer": "Based on the provided context, this document discusses...",
  "sources": [
    {
      "document_id": "my-document",
      "chunk_id": "0",
      "source": "My Document.pdf",
      "page": 1,
      "snippet": "First 200 characters of the chunk used..."
    },
    {
      "document_id": "my-document",
      "chunk_id": "1",
      "source": "My Document.pdf",
      "page": 1,
      "snippet": "..."
    }
  ],
  "context_used": 3456,
  "model_used": "ai/qwen3:latest"
}
```

**Empty Result Response (200):**
```json
{
  "answer": "I don't know based on the provided document(s).",
  "sources": [],
  "context_used": 0,
  "model_used": "ai/qwen3:latest"
}
```

**Error Responses:**
- `400`: Invalid request (question too short, top_k out of range)
- `500`: Server error (embedding failure, retrieval error, LLM error)

---

## 3. Health Checks

### `GET /health` (All Services)

Check service health status.

**Endpoints:**
- `http://localhost:8001/health` (Ingestion Service)
- `http://localhost:8002/health` (Query Service)
- `http://localhost:8003/health` (Search Service)

**Example:**
```javascript
const response = await fetch('http://localhost:8002/health');
const result = await response.json();
// {
//   "status": "ok",
//   "service": "rag-query-service",
//   "timestamp": "2024-01-15 10:30:45 AM"
// }
```

**Search Service Health Response:**
```json
{
  "status": "ok",
  "opensearch": {
    "cluster_name": "docker-cluster",
    "cluster_uuid": "...",
    "version": "2.17.0",
    "index": "docs_bm25"
  }
}
```

---

## 4. BM25 Search (Advanced / Debug)

### `POST /search` (Search Service)

Direct BM25 keyword search (useful for debugging or advanced use cases).

**Endpoint:** `http://localhost:8003/search`

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query": "search terms",
  "top_k": 10,
  "document_ids": ["doc1", "doc2"],  // optional filter
  "sources": ["file1.pdf"]           // optional filter
}
```

**Fields:**
- `query` (required, min 1 char): Search query
- `top_k` (optional, default 10, range 1-50): Number of hits to return
- `document_ids` (optional): Filter by document IDs
- `sources` (optional): Filter by source filenames

**Example:**
```javascript
const response = await fetch('http://localhost:8003/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'experience',
    top_k: 10
  })
});

const result = await response.json();
// {
//   "hits": [
//     {
//       "document_id": "cover-letter",
//       "chunk_id": 0,
//       "source": "Cover Letter.pdf",
//       "page": 1,
//       "text": "Full chunk text...",
//       "tags": [],
//       "score": 8.234
//     }
//   ],
//   "total": 1
// }
```

**Response:**
```json
{
  "hits": [
    {
      "document_id": "cover-letter",
      "chunk_id": 0,
      "source": "Cover Letter.pdf",
      "page": 1,
      "text": "Full chunk text content...",
      "tags": [],
      "score": 8.234
    }
  ],
  "total": 1
}
```

---

## 5. Index Document (Internal / Advanced)

### `POST /index` (Search Service)

Index a single chunk into OpenSearch (typically called by ingestion-service, but available for direct use).

**Endpoint:** `http://localhost:8003/index`

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "document_id": "my-document",
  "chunk_id": 0,
  "source": "My Document.pdf",
  "page": 1,
  "text": "Chunk text content...",
  "tags": ["tag1", "tag2"]  // optional
}
```

**Response:**
```json
{
  "index": "docs_bm25",
  "id": "auto-generated-id",
  "result": "created"
}
```

---

## TypeScript Types

```typescript
// Ingestion
interface IngestRequest {
  file: File;
  document_id?: string;
  source?: string;
  version?: string;
}

interface IngestResponse {
  status: string;
  document_id: string;
  characters: number;
  chunks: number;
  embedding_dim: number;
  preview: string | null;
}

// Query
interface QueryRequest {
  question: string;
  top_k?: number;  // 1-20, default 5
  model_name?: string;
  document_id?: string;
}

interface Source {
  document_id: string;
  chunk_id: string;
  source: string | null;
  page: number | null;
  snippet: string | null;
}

interface QueryResponse {
  answer: string;
  sources: Source[];
  context_used: number;
  model_used: string;
}

// BM25 Search
interface BM25SearchRequest {
  query: string;
  top_k?: number;  // 1-50, default 10
  document_ids?: string[];
  sources?: string[];
}

interface BM25SearchHit {
  document_id: string;
  chunk_id: number;
  source: string | null;
  page: number | null;
  text: string;
  tags: string[];
  score: number;
}

interface BM25SearchResponse {
  hits: BM25SearchHit[];
  total: number;
}

// Health
interface HealthResponse {
  status: string;
  service?: string;
  timestamp?: string;
  opensearch?: {
    cluster_name: string;
    cluster_uuid: string;
    version: string;
    index: string;
  };
}
```

---

## Error Handling

All endpoints may return standard HTTP error codes:

- **400 Bad Request:** Invalid input (file type, question length, etc.)
- **500 Internal Server Error:** Server-side error (embedding failure, database error, etc.)
- **503 Service Unavailable:** Dependent service unavailable (OpenSearch down, etc.)

**Error Response Format:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

**Example Error Handling:**
```javascript
try {
  const response = await fetch('http://localhost:8002/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: 'test' })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  const result = await response.json();
  // Handle success
} catch (error) {
  // Handle network or parsing errors
  console.error('Query failed:', error);
}
```

---

## CORS Configuration

If your frontend runs on a different origin (e.g., `http://localhost:3000`), you may need to configure CORS in the FastAPI services:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Rate Limiting

Currently, no rate limiting is implemented. For production, consider adding rate limiting middleware.

---

## WebSocket / Streaming (Future)

Currently, all endpoints are synchronous HTTP. For streaming LLM responses, you would need to:

1. Modify `query-service/app/services/llm.py` to support streaming
2. Change `/query` endpoint to return `StreamingResponse`
3. Update frontend to handle Server-Sent Events (SSE) or WebSocket

---

## Example Frontend Integration

```javascript
// services/api.js
const API_BASE = {
  ingestion: 'http://localhost:8001',
  query: 'http://localhost:8002',
  search: 'http://localhost:8003'
};

export const ingestDocument = async (file, documentId, source) => {
  const formData = new FormData();
  formData.append('file', file);
  if (documentId) formData.append('document_id', documentId);
  if (source) formData.append('source', source);

  const response = await fetch(`${API_BASE.ingestion}/ingest`, {
    method: 'POST',
    body: formData
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }

  return response.json();
};

export const query = async (question, topK = 5, documentId = null) => {
  const body = { question, top_k: topK };
  if (documentId) body.document_id = documentId;

  const response = await fetch(`${API_BASE.query}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }

  return response.json();
};

export const checkHealth = async (service) => {
  const response = await fetch(`${API_BASE[service]}/health`);
  return response.json();
};
```

---

This API reference provides everything needed to integrate a frontend with the RAG Micro services.

