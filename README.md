# 💼 AskHR Chatbot

A production-grade **Retrieval-Augmented Generation (RAG)** chatbot for HR-related queries, built with FastAPI, LangChain, ChromaDB, and a Streamlit chat frontend — fully containerised with Docker Compose.

Supports **OpenAI** (GPT-4o) and **HuggingFace** (Inference API or local model loading) as interchangeable LLM providers, switchable per-session from the chat UI.

---

## Features

- **Dual LLM provider** — switch between **OpenAI** (GPT-4o) and **HuggingFace** (Inference API or local weights) per-session from the Streamlit sidebar, with no backend restart required
- **Configurable embeddings** — use OpenAI or HuggingFace sentence-transformers for ChromaDB, controlled via `EMBEDDING_PROVIDER`
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
| LLM (OpenAI) | OpenAI GPT-4o |
| LLM (HuggingFace) | Any HF model via Inference API or local pipeline |
| Embeddings (OpenAI) | `text-embedding-3-small` |
| Embeddings (HuggingFace) | `BAAI/bge-small-en-v1.5` (sentence-transformers) |
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
- At least one of:
  - An **OpenAI API key** (`OPENAI_API_KEY`) — for the OpenAI provider
  - A **HuggingFace token** (`HF_API_TOKEN`) — for HuggingFace Inference API mode
  - No token needed for HuggingFace **local** mode (requires significant RAM/VRAM and `transformers` + `torch`)

### 1. Clone and configure

```bash
git clone <repo-url>
cd AskHRchatbot
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and/or HF_API_TOKEN
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

> **Note:** The embedding model used at ingest time must match the one used at query time. Set `EMBEDDING_PROVIDER` (and related model vars) **before** your first ingest and keep it consistent.

### 5. Start chatting

Open http://localhost:8501 and ask HR questions like:

- *"How many annual leave days do I get?"*
- *"What is the remote work policy?"*
- *"How do I submit an expense report?"*

Use the **🤖 LLM Provider** section in the sidebar to switch between **OpenAI** and **HuggingFace** at any time. Your conversation history is preserved across provider switches.

---

## API Reference

### `POST /api/v1/chat` — Streaming (SSE)

```json
{
  "session_id": "uuid",
  "message": "What is the leave policy?",
  "provider": "openai",
  "hf_access_mode": "api"
}
```

`provider` can be `"openai"` or `"huggingface"`. `hf_access_mode` is `"api"` (HuggingFace Inference API) or `"local"` (load weights locally); ignored when `provider` is `"openai"`.

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

### Provider

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Startup default shown in the sidebar (`openai` \| `huggingface`). Users can override per-session. |
| `EMBEDDING_PROVIDER` | `openai` | Embedding backend used for ChromaDB ingestion and retrieval (`openai` \| `huggingface`). Set before first ingest. |

### OpenAI

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required when using the OpenAI provider |
| `LLM_MODEL` | `gpt-4o` | OpenAI chat model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model (used when `EMBEDDING_PROVIDER=openai`) |
| `LLM_TEMPERATURE` | `0.2` | LLM response temperature |

### HuggingFace

| Variable | Default | Description |
|---|---|---|
| `HF_API_TOKEN` | — | HuggingFace Hub token. Required for `hf_access_mode=api`. |
| `HF_LLM_MODEL` | `meta-llama/Llama-3-8B-Instruct` | Default HF chat model |
| `HF_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | HF embedding model (used when `EMBEDDING_PROVIDER=huggingface`) |
| `HF_ACCESS_MODE` | `api` | Server-level default: `api` (Inference API) or `local` (download weights) |

> **Local mode** requires `transformers` and `torch` to be installed (not included in `requirements.txt` due to size). Install them manually: `pip install transformers torch`.

### General

| Variable | Default | Description |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB storage path |
| `CHROMA_COLLECTION_NAME` | `askhr_docs` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Document chunk size (tokens) |
| `CHUNK_OVERLAP` | `200` | Chunk overlap (tokens) |
| `RETRIEVER_K` | `5` | Number of chunks retrieved per query |
| `MEMORY_WINDOW` | `10` | Number of past conversation turns to retain |
| `RATE_LIMIT` | `20/minute` | API rate limit per IP |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins |

---

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v
```

Tests use `pytest-asyncio` and mock the RAGService so no API key or ChromaDB is required.

---

## Development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set OPENAI_API_KEY and/or HF_API_TOKEN

# (Optional) install local-mode HuggingFace dependencies
# pip install transformers torch

# Run backend
uvicorn app.main:app --reload --port 8000

# Run frontend (separate terminal)
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

