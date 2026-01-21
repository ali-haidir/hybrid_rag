# RAG Micro – End-to-End Testing Checklist (0 → Full)

> Goal: validate the full lifecycle from a clean system → ingestion → indexing (Chroma + OpenSearch) → hybrid retrieval → answer + sources.

## Conventions used in commands

- Replace service names if your `docker compose` uses different ones (examples below assume: `query-service`, `search-service`, `opensearch`, and `chroma`).
- Replace ports if yours differ (examples below assume: query-service `8002`, search-service `8003`, OpenSearch `9200`, Chroma `8000`).
- This repo uses OPENSEARCH_INDEX=docs_bm25 (see your .env).
- In commands below, <OPENSEARCH_INDEX> defaults to docs_bm25.

---

## 0) Pre-flight (one-time / before every full run)

- [ ] **Confirm environment variables are set**
  - [ ] `MODEL_EMBED` set
  - [ ] `MODEL_CHAT` set (or default works)
  - [ ] `OPENAI_API_KEY` / `BASE_URL` set (as required by your embedding/chat backend)
  - [ ] OPENSEARCH_INDEX set (expected: docs_bm25)
  - [ ] Hybrid knobs (optional):
    - [ ] `HYBRID_BM25_CHUNKS`
    - [ ] `HYBRID_CENTER_K`
    - [ ] `HYBRID_NEIGHBOR_WINDOW`
    - [ ] `HYBRID_MAX_CONTEXT_CHUNKS`
    - [ ] `HYBRID_FUSION_ALPHA`
    - [ ] `HYBRID_CENTER_REL_THRESHOLD`
    - [ ] `HYBRID_DISTANCE_PENALTY`

### Commands

```bash
# Show relevant env vars on your host
printenv | egrep 'MODEL_|OPENAI_|BASE_URL|HYBRID_|OPENSEARCH_INDEX' || true

# Show env vars inside query-service (recommended)
docker compose exec -T query-service env | egrep 'MODEL_|OPENAI_|BASE_URL|HYBRID_|OPENSEARCH_INDEX' || true
```

- [ ] **Confirm services are reachable**
  - [ ] query-service is up
  - [ ] ingest-service is up (if separate)
  - [ ] search-service is up
  - [ ] OpenSearch container is healthy / reachable
  - [ ] Chroma persistence path / container is healthy

### Commands

```bash
# Container health / status
docker compose ps

# FastAPI docs endpoints are a quick sanity check (adjust ports if needed)
curl -s -o /dev/null -w "query-service /docs -> %{http_code}\n" http://localhost:8002/docs
curl -s -o /dev/null -w "search-service /docs -> %{http_code}\n" http://localhost:8003/docs

# OpenSearch root info (should return JSON)
curl -s http://localhost:9200 | head

# Chroma heartbeat (if running as a server)
curl -s http://localhost:8000/api/v1/heartbeat || true
```

- [ ] **Turn on useful logging for this test run**
  - [ ] query-service logs show: BM25 calls, Chroma.get IDs, selected centers, stitched counts
  - [ ] search-service logs show: index ensure + query hits count

---

## 1) Stop stack (optional but recommended for “clean slate”)

- [ ] Stop all containers cleanly
- [ ] Confirm no old containers keep volumes locked

### Commands

```bash
# Stop everything (keeps volumes)
docker compose down

# Stop everything AND remove named volumes (strong reset)
docker compose down -v
```

---

## 2) Drop data from volumes (RESET)

> Objective: start from a truly empty state.

- [ ] **Drop Chroma data**
  - [ ] Remove Chroma persistent volume / data directory
  - [ ] Confirm Chroma storage directory is empty

### Commands

```bash
# Option A (recommended): remove all project volumes
# WARNING: deletes all persistent data for this compose project
docker compose down -v

# Option B: remove ONLY specific volumes (replace names)
docker volume ls | egrep 'chroma|opensearch|rag_micro' || true
# Example:
# docker volume rm rag_micro_chroma_data rag_micro_opensearch_data

# Option C: if you use bind-mount folders, delete the data dirs (replace paths)
# rm -rf ./data/chroma ./data/opensearch
```

- [ ] **Drop OpenSearch data**

  - [ ] Remove OpenSearch persistent volume / data directory
  - [ ] Confirm OpenSearch data directory is empty

- [ ] **Drop any app caches (if present)**
  - [ ] BM25 index cache (if you cache locally)
  - [ ] local embeddings cache (if you cache)

---

## 3) Verify data is actually dropped

- [ ] Start only the storage services (OpenSearch + Chroma)

```bash
# Start only storage services (adjust service names)
docker compose up -d opensearch chroma

docker compose ps
```

- [ ] **Chroma check**
  - [ ] Collections list is empty OR expected collections exist but contain 0 items
  - [ ] A simple `count()` (or equivalent) returns 0

```bash
# If Chroma is an HTTP server (common): list collections via Python client
python - <<'PY'
import os
import chromadb
host=os.getenv('CHROMA_HOST','localhost')
port=int(os.getenv('CHROMA_PORT','8000'))
client=chromadb.HttpClient(host=host, port=port)
cols=client.list_collections()
print('collections:', [c.name for c in cols])
for c in cols:
    col=client.get_collection(c.name)
    print(c.name, 'count=', col.count())
PY

# Quick curl sanity check (may vary by Chroma version)
curl -s http://localhost:8000/api/v1/heartbeat || true
```

- [ ] **OpenSearch check**
  - [ ] Indices list does not contain your target index OR
  - [ ] Index exists but doc count is 0

```bash
# Indices list
curl -s "http://localhost:9200/_cat/indices?v" || true

# If your index exists, verify doc count is 0 (replace <OPENSEARCH_INDEX>)
curl -s "http://localhost:9200/docs_bm25/_count" | head
```

- [ ] If any data remains → repeat Step 2

---

## 4) Start full stack

- [ ] Start all services
- [ ] Confirm each service is healthy
- [ ] Confirm search-service can connect to OpenSearch (no connection refused)

> If you see OpenSearch connection refused in search-service logs, wait for OpenSearch to become healthy or restart search-service.

### Commands

```bash
# Start everything
docker compose up -d

docker compose ps

# Watch logs (Ctrl+C to stop)
docker compose logs -f --tail=200 query-service search-service opensearch chroma
```

---

## 5) Ingest data (end-to-end)

> Objective: ingest documents so they appear in BOTH Chroma and OpenSearch.

- [ ] Ingest the test dataset (minimum recommended):

  - [ ] `Cover Latter.pdf` (or your “experience” document)
  - [ ] `AWS Certified AI Practitioner Slides v16.pdf` (or your “VPC” document)

- [ ] Confirm ingestion pipeline completed without errors
  - [ ] Chunking succeeded
  - [ ] Embeddings generated successfully
  - [ ] Upserts to Chroma succeeded
  - [ ] Upserts to OpenSearch succeeded

### Commands

```bash
# If you have an ingest-service with a FastAPI endpoint, this is a common pattern.
# Adjust URL/fields to match your ingest API.

# Example: ingest Cover Letter
curl -X POST "http://localhost:8001/ingest" \
  -F "file=@./data/Cover Latter.pdf" \
  -F "document_id=cover latter" \
  -F "source=Cover Latter.pdf"

# Example: ingest AWS slides
curl -X POST "http://localhost:8001/ingest" \
  -F "file=@./data/AWS Certified AI Practitioner Slides v16.pdf" \
  -F "document_id=aws slides" \
  -F "source=AWS Certified AI Practitioner Slides v16.pdf"

# If ingestion is a CLI script instead, run it here (example)
# python -m app.ingest --path ./data
```

---

## 6) Verify ingestion results in Chroma

- [ ] Verify expected collection exists
- [ ] Verify total chunk count is > 0
- [ ] Spot-check:
  - [ ] A known chunk ID exists (e.g., `cover latter::0`)
  - [ ] A known AWS slide chunk exists (e.g., `aws slides::339`)
- [ ] Verify metadata integrity:
  - [ ] `document_id` present
  - [ ] `chunk_id` present and numeric
  - [ ] `source` and `page` present (if expected)

### Commands

```bash
# Verify specific IDs exist (requires access to the same Chroma backend used by your app)
python - <<'PY'
import os
import chromadb
host=os.getenv('CHROMA_HOST','localhost')
port=int(os.getenv('CHROMA_PORT','8000'))
collection=os.getenv('CHROMA_COLLECTION','rag')  # replace if needed
client=chromadb.HttpClient(host=host, port=port)
col=client.get_collection(collection)
print('count=', col.count())
print('get cover latter::0 ->')
print(col.get(ids=['cover latter::0'], include=['metadatas','documents']).get('ids'))
print('get aws slides::339 ->')
print(col.get(ids=['aws slides::339'], include=['metadatas','documents']).get('ids'))
PY
```

---

## 7) Verify ingestion results in OpenSearch (BM25)

- [ ] Verify index exists
- [ ] Verify doc count > 0
- [ ] Run a direct search-service query (BM25) and confirm top hits make sense:
  - [ ] Query: “how much experience does ali haider has?”
    - [ ] `cover latter` appears in top hits
  - [ ] Query: “tell me about vpc”
    - [ ] `aws slides` VPC-related chunk appears in top hits

### Commands

```bash
# Verify OpenSearch index exists + doc count (replace <OPENSEARCH_INDEX>)
curl -s "http://localhost:9200/_cat/indices?v" | head
curl -s "http://localhost:9200/docs_bm25/_count" | head

# Mapping sanity check (optional)
curl -s "http://localhost:9200/docs_bm25/_mapping" | head

# Prefer testing BM25 through your search-service (this matches production flow)
curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query":"how much experience does ali haider has?","top_k":5}'

curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query":"tell me about vpc","top_k":5}'
```

---

## 8) Query flow validation (Hybrid RAG)

> Objective: verify the exact hybrid pipeline works as intended:
> BM25 → Chroma.get(centers) → fuse/rerank → neighbor stitching → LLM → sources.

### 8.1) Test query: Experience

- [ ] Call `/query` with:
  - [ ] question: “how much experience does ali haider has?”
  - [ ] top_k: 5

```bash
curl -X POST http://localhost:8002/query \
  -H "Content-Type: application/json" \
  -d '{"question":"how much experience does ali haider has?","top_k":5,"model_name":"ai/qwen3:latest"}'
```

- [ ] Validate logs show expected flow:

  - [ ] BM25 called with correct `top_k` and returns hits
  - [ ] Chroma.get requested IDs include `cover latter::0`
  - [ ] Selected centers include a `cover latter` center (even if not rank #1)
  - [ ] Stitched docs include at least 1 `cover latter` chunk

- [ ] Validate response correctness:
  - [ ] Answer contains “over four years” (or the exact ground truth)
  - [ ] Sources list contains a `cover latter` citation with page + snippet

### 8.2) Test query: VPC

- [ ] Call `/query` with:
  - [ ] question: “tell me about vpc”
  - [ ] top_k: 5

```bash
curl -X POST http://localhost:8002/query \
  -H "Content-Type: application/json" \
  -d '{"question":"tell me about vpc","top_k":5,"model_name":"ai/qwen3:latest"}'
```

- [ ] Validate logs show expected flow:

  - [ ] BM25 returns VPC-relevant hits
  - [ ] Selected centers are from VPC section
  - [ ] Stitched docs include contiguous VPC chunks (neighbors)

- [ ] Validate response correctness:
  - [ ] Answer mentions VPC basics (VPC, subnets, IGW/NAT, CIDR)
  - [ ] Sources cite the VPC pages/chunks

---

## 9) Ranking + citation quality checks

- [ ] Sources are **deduped** by `(document_id, chunk_id)`
- [ ] Sources are **ranked** by evidence strength:
  - [ ] neighbors have `evidence_score`
  - [ ] centers have `center_score`
- [ ] The most relevant citation appears near the top

---

## 10) Negative / edge case testing

- [ ] Unknown question with no matching content

  - [ ] Returns “I don’t know based on provided documents”
  - [ ] Returns empty sources

- [ ] Document-scoped query (if supported)

  - [ ] Provide `document_id` and confirm BM25 is skipped and vector search is constrained

- [ ] Very short question (1–2 words)

  - [ ] Doesn’t crash
  - [ ] Still returns reasonable sources

- [ ] Very long question
  - [ ] Doesn’t exceed embedding/LLM limits (or fails gracefully)

---

## 11) Reliability + regression checks

- [ ] Repeat the same query 3–5 times

  - [ ] Results are stable (sources and answer roughly consistent)

- [ ] Restart only query-service

  - [ ] Retrieval still works (no state lost)

- [ ] Restart OpenSearch only

  - [ ] search-service reconnects
  - [ ] BM25 works again

- [ ] Restart Chroma only
  - [ ] retrieval still works after it comes back

```bash
# Repeat the same query multiple times to check stability
for i in 1 2 3 4 5; do
  echo "--- run $i";
  curl -s -X POST http://localhost:8002/query \
    -H "Content-Type: application/json" \
    -d '{"question":"tell me about vpc","top_k":5,"model_name":"ai/qwen3:latest"}' \
  | head -c 400; echo; echo;
done

# Restart just one service (example: query-service)
docker compose restart query-service

docker compose logs -f --tail=100 query-service
```

---

## 12) Performance sanity checks (quick)

- [ ] Measure approximate latency for:

  - [ ] Embedding call
  - [ ] BM25 search
  - [ ] Chroma.get + stitching
  - [ ] LLM generation

- [ ] Ensure no step is unexpectedly slow (e.g., BM25 timing out)

```bash
# Basic end-to-end timing (embedding+bm25+chroma+llm)
time curl -s -X POST http://localhost:8002/query \
  -H "Content-Type: application/json" \
  -d '{"question":"tell me about vpc","top_k":5,"model_name":"ai/qwen3:latest"}' \
  > /dev/null
```

---

## 13) Final “green” criteria

- [ ] Clean reset works (Step 2–3)
- [ ] Ingest populates **both** Chroma and OpenSearch
- [ ] Hybrid query flow is correct and visible in logs
- [ ] Answers are grounded in the correct documents
- [ ] Sources cite the right doc/chunk/page and are ranked sensibly

---

## Notes / Observations (fill in during testing)

- Run date/time:
- Dataset used:
- Issues found:
- Fixes applied:
- Follow-ups / next sprint items:
