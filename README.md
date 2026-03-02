# 💼 AskHR Chatbot

A production-grade **Retrieval-Augmented Generation (RAG)** chatbot for HR-related queries, built with FastAPI, LangChain, OpenAI GPT-4o, ChromaDB, and a Streamlit chat frontend — fully containerised with Docker Compose.

---

## Features

- **Conversational RAG** — multi-turn chat with per-session memory (window of 10 exchanges)
- **SSE streaming** — real-time token-by-token response delivery
- **MMR retrieval** — Maximal Marginal Relevance retrieval for diverse, non-redundant context
- **Multi-format ingestion** — PDF, DOCX, and web URLs
- **File upload API** — upload HR documents directly via REST
- **Rate limiting** — SlowAPI middleware (20 req/min per IP by default)
- **Structured logging** — Loguru with rotating log files
- **Source citations** — every answer links back to the source documents/pages

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | OpenAI GPT-4o |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector DB | ChromaDB (persistent) |
| RAG framework | LangChain |
| Backend API | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Containerisation | Docker + Docker Compose |

---

## Project Structure

```
AskHRchatbot/
├── app/
│   ├── main.py                    # FastAPI app factory + lifespan startup
│   ├── api/routes/
│   │   ├── chat.py                # POST /api/v1/chat (SSE stream), /chat/sync, DELETE /{session_id}
│   │   └── ingest.py              # POST /api/v1/ingest, /ingest/upload
│   ├── core/
│   │   ├── config.py              # pydantic-settings env config
│   │   └── logging.py             # Loguru structured logging
│   ├── db/
│   │   └── chroma_client.py       # ChromaDB singleton persistent client
│   ├── models/
│   │   └── schemas.py             # Pydantic request / response models
│   └── services/
│       ├── ingest_service.py      # Document loading → chunking → embedding → ChromaDB
│       └── rag_service.py         # ConversationalRetrievalChain + per-session memory
├── frontend/
│   ├── app.py                     # Streamlit chat UI
│   ├── Dockerfile
│   └── requirements.txt
├── data/
│   ├── documents/                 # Drop HR PDF / DOCX files here
│   └── web_sources.txt            # One URL per line to crawl
├── chroma_db/                     # Persisted vector data (Docker volume)
├── tests/
│   ├── conftest.py
│   ├── test_chat.py
│   └── test_ingest.py
├── .env.example
├── .dockerignore
├── Dockerfile                     # Multi-stage backend image
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- An OpenAI API key

### 1. Clone and configure

```bash
git clone <repo-url>
cd AskHRchatbot
cp .env.example .env
# Open .env and set your OPENAI_API_KEY
```

### 2. Add HR documents

Place your HR policy PDFs and/or DOCX files in `data/documents/`.  
Optionally add web URLs (one per line) to `data/web_sources.txt`.

### 3. Start the stack

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI (Streamlit) | http://localhost:8501 |
| REST API (FastAPI) | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

### 4. Ingest HR documents

Trigger ingestion via the Streamlit sidebar **"Re-index Documents"** panel, or directly:

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"reindex": false}'
```

Use `"reindex": true` to wipe and rebuild the vector index from scratch.

### 5. Start chatting

Open http://localhost:8501 and ask HR questions like:

- *"How many annual leave days do I get?"*
- *"What is the remote work policy?"*
- *"How do I submit an expense report?"*

---

## API Reference

### `POST /api/v1/chat` — Streaming (SSE)

```json
{ "session_id": "uuid", "message": "What is the leave policy?" }
```

Returns a `text/event-stream` of token events, with a final event containing the full answer and source documents.

### `POST /api/v1/chat/sync` — Non-streaming

Same request body. Returns a JSON response:

```json
{
  "session_id": "uuid",
  "answer": "...",
  "sources": [{ "source": "leave_policy.pdf", "page": 1, "content_preview": "..." }]
}
```

### `DELETE /api/v1/chat/{session_id}` — Clear session memory

### `POST /api/v1/ingest` — Trigger ingestion

```json
{ "urls": ["https://example.com/hr-policy"], "reindex": false }
```

### `POST /api/v1/ingest/upload` — Upload a file

Upload a PDF or DOCX via `multipart/form-data` (`file` field).

### `GET /health`

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## Configuration

All settings are controlled via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key |
| `LLM_MODEL` | `gpt-4o` | OpenAI chat model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `LLM_TEMPERATURE` | `0.2` | LLM response temperature |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB storage path |
| `CHROMA_COLLECTION_NAME` | `askhr_docs` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Document chunk size (tokens) |
| `CHUNK_OVERLAP` | `200` | Chunk overlap (tokens) |
| `RETRIEVER_K` | `5` | Number of chunks retrieved per query |
| `RATE_LIMIT` | `20/minute` | API rate limit per IP |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins (comma-separated) |

---

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v
```

Tests use `pytest-asyncio` and mock the RAGService so no OpenAI API key or ChromaDB is required.

---

## Development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set OPENAI_API_KEY

# Run backend
uvicorn app.main:app --reload --port 8000

# Run frontend (separate terminal)
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

