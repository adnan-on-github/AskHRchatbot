# AskHR Chatbot — Setup & Usage Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development (without Docker)](#local-development-without-docker)
3. [Local Development (with Docker)](#local-development-with-docker)
4. [Adding HR Documents](#adding-hr-documents)
5. [Ingesting Documents](#ingesting-documents)
6. [Using the Chat UI](#using-the-chat-ui)
7. [Using the REST API](#using-the-rest-api)
8. [Azure Deployment](#azure-deployment)
9. [Running Tests](#running-tests)
10. [Configuration Reference](#configuration-reference)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.12 | Local dev only |
| Docker | 24+ | For container setup |
| Docker Compose | v2 | Bundled with Docker Desktop |
| Azure CLI | 2.60+ | Azure deployment only |
| OpenAI API key **or** Azure OpenAI resource | — | Required for LLM + embeddings |

---

## Local Development (without Docker)

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd AskHRchatbot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate       # Linux / macOS
# .venv\Scripts\activate        # Windows
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```ini
# Standard OpenAI
OPENAI_API_KEY=sk-...

# OR Azure OpenAI (local dev with API key)
USE_MANAGED_IDENTITY=false
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### 5. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### 6. Start the frontend (separate terminal)

```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## Local Development (with Docker)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY or Azure OpenAI variables
```

### 2. Build and start both services

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI (Streamlit) | http://localhost:8501 |
| REST API (FastAPI) | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 3. Stop services

```bash
docker compose down
```

> ChromaDB data persists in `./chroma_db/` between restarts.

---

## Adding HR Documents

### Option A — File system (before starting)

Drop PDF or DOCX files into the `data/documents/` directory:

```
data/
└── documents/
    ├── employee-handbook.pdf
    ├── leave-policy.pdf
    ├── benefits-guide.docx
    └── remote-work-policy.pdf
```

### Option B — Web URLs

Add URLs (one per line) to `data/web_sources.txt`:

```
# HR portal pages
https://yourcompany.com/hr/leave-policy
https://yourcompany.com/hr/benefits
https://yourcompany.com/hr/remote-work
```

Lines beginning with `#` are ignored.

### Option C — Upload via API

Upload a single file directly without restarting:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/upload \
  -F "file=@/path/to/policy.pdf"
```

---

## Ingesting Documents

Ingestion must be triggered manually after adding documents. It runs as a background task and returns immediately.

### Via Streamlit sidebar

1. Open `http://localhost:8501`
2. In the left sidebar → **Admin** → **Re-index Documents**
3. Optionally add extra URLs and toggle **Wipe & rebuild index**
4. Click **▶ Run Ingestion**

### Via REST API

```bash
# Basic ingest (new documents only)
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{}'

# Include extra URLs
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://yourcompany.com/hr/policy"],
    "reindex": false
  }'

# Full rebuild (wipes existing index)
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"reindex": true}'
```

> Ingestion progress is logged to the backend console and `logs/askhr.log`.

---

## Using the Chat UI

1. Open `http://localhost:8501`
2. Type your HR question in the input box at the bottom
3. The answer streams in real time, token by token
4. Expand **📄 Sources** under any answer to see which documents were cited
5. Use **🗑️ Clear Conversation** in the sidebar to reset the session

### Example questions

- *"How many annual leave days am I entitled to?"*
- *"What is the process for submitting a expense claim?"*
- *"Can I work remotely full time?"*
- *"How do I enrol in the health insurance plan?"*
- *"What happens to unused leave at year end?"*

---

## Using the REST API

Full interactive documentation is available at `http://localhost:8000/docs`.

### Stream chat (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-session-001",
    "message": "What is the leave policy?"
  }'
```

Returns `text/event-stream`. Each event is a JSON object:

```
data: {"token": "You "}
data: {"token": "are "}
data: {"token": "entitled..."}
data: {"done": true, "answer": "You are entitled to...", "sources": [...]}
data: [DONE]
```

### Sync chat (JSON)

```bash
curl -X POST http://localhost:8000/api/v1/chat/sync \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-session-001",
    "message": "What is the leave policy?"
  }'
```

Response:

```json
{
  "session_id": "my-session-001",
  "answer": "Employees are entitled to 20 days of annual leave per year...",
  "sources": [
    {
      "source": "leave-policy.pdf",
      "page": 3,
      "content_preview": "Annual leave entitlement is 20 working days..."
    }
  ]
}
```

### Clear session memory

```bash
curl -X DELETE http://localhost:8000/api/v1/chat/my-session-001
```

Returns `204 No Content`. The next message on this `session_id` starts a fresh conversation.

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok", "version": "1.0.0"}
```

---

## Azure Deployment

### Prerequisites

- Azure CLI installed and logged in: `az login`
- Contributor + User Access Administrator permissions on your subscription
- An existing Azure OpenAI resource with `gpt-4o` and `text-embedding-3-small` models deployed

### 1. Edit the provisioning script

Open `infra/provision.sh` and fill in:

```bash
AZURE_OPENAI_RESOURCE_ID="/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<NAME>"
AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
ACR_NAME="<globally-unique-acr-name>"
```

### 2. Provision all Azure resources

```bash
chmod +x infra/provision.sh
bash infra/provision.sh
```

This creates in one shot:
- Resource group
- Azure Container Registry (ACR)
- Storage account + Azure Files share (for ChromaDB persistence)
- User-assigned Managed Identity
- Container Apps environment
- Backend + frontend Container Apps
- Role assignments (OpenAI User, AcrPull)

### 3. Set up Azure DevOps pipeline

1. In Azure DevOps → **Project Settings** → **Service connections**, create:
   - `AzureSubscription` — Azure Resource Manager (Contributor scope)
   - `AskHR-ACR` — Docker Registry pointing at your ACR

2. Add pipeline variables (Pipelines → your pipeline → Variables):

   | Variable | Example value |
   |---|---|
   | `ACR_NAME` | `askhrregistry` |
   | `RESOURCE_GROUP` | `rg-askhr` |
   | `CONTAINERAPPS_ENV` | `cae-askhr` |

3. Import `azure-pipelines.yml` as a new pipeline.

### 4. Deploy

Push to `main` → the pipeline runs automatically:

```
Stage 1: Test     → pytest
Stage 2: Build    → docker build + push to ACR
Stage 3: Deploy   → az containerapp update (backend + frontend)
```

### 5. Ingest documents in Azure

```bash
BACKEND_URL=$(az containerapp show \
  --name askhr-backend \
  --resource-group rg-askhr \
  --query properties.configuration.ingress.fqdn -o tsv)

# Upload a document
curl -X POST https://$BACKEND_URL/api/v1/ingest/upload \
  -F "file=@leave-policy.pdf"

# Or trigger ingest of pre-loaded documents
curl -X POST https://$BACKEND_URL/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{}'
```

> ChromaDB data persists to the Azure Files share mounted at `/mnt/chromadb` — survives container restarts and redeployments.

---

## Running Tests

```bash
# Activate virtualenv first
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing
```

Tests mock the RAGService and IngestService — no OpenAI API key or ChromaDB required to run the test suite.

---

## Configuration Reference

All settings are loaded from environment variables (or `.env` file).

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `""` | Standard OpenAI API key (local dev) |
| `USE_MANAGED_IDENTITY` | `false` | Set `true` in Azure to use keyless auth |
| `AZURE_OPENAI_ENDPOINT` | `""` | Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_API_KEY` | `""` | Azure OpenAI key (only if not using MI) |
| `AZURE_OPENAI_API_VERSION` | `2024-02-01` | Azure OpenAI API version |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | `gpt-4o` | Chat model deployment name in Azure |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-small` | Embedding deployment name in Azure |
| `AZURE_CLIENT_ID` | `""` | Client ID of user-assigned Managed Identity |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB storage path (`/mnt/chromadb` in Azure) |
| `CHROMA_COLLECTION_NAME` | `askhr_docs` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Document chunk size in characters |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `RETRIEVER_K` | `5` | Number of chunks retrieved per query |
| `LLM_MODEL` | `gpt-4o` | OpenAI model (non-Azure path) |
| `LLM_TEMPERATURE` | `0.2` | LLM response temperature (0 = deterministic) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model (non-Azure path) |
| `MEMORY_WINDOW` | `10` | Number of past exchanges kept per session |
| `RATE_LIMIT` | `20/minute` | API rate limit per IP address |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `ALLOWED_ORIGINS` | `*` | CORS origins (comma-separated or `*`) |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL used by the Streamlit frontend |

---

## Troubleshooting

### `ChromaDB` errors on startup

The vectorstore is empty if ingestion has never run. Trigger ingestion first:

```bash
curl -X POST http://localhost:8000/api/v1/ingest -H "Content-Type: application/json" -d '{}'
```

### `openai.AuthenticationError`

- Check `OPENAI_API_KEY` is set correctly in `.env`
- For Azure: verify `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` are correct
- For Managed Identity: ensure the identity has the **Cognitive Services OpenAI User** role on the Azure OpenAI resource

### Streamlit shows "Backend: Unreachable"

- Backend is not running or the `BACKEND_URL` env var is wrong
- Docker: check `docker compose ps` — backend container must be healthy
- Local: confirm `uvicorn` is running on port 8000

### No sources returned with answers

- Documents have not been ingested yet — run `/api/v1/ingest`
- Documents may be in an unsupported format — only PDF, DOCX, and URLs are supported
- Check backend logs: `docker compose logs backend` or `logs/askhr.log`

### Azure Container App — container failing to start

```bash
az containerapp logs show \
  --name askhr-backend \
  --resource-group rg-askhr \
  --follow
```

Common causes:
- Missing environment variables (`AZURE_OPENAI_ENDPOINT`, `USE_MANAGED_IDENTITY`)
- Managed Identity not yet propagated — wait ~60 seconds after role assignment and retry
- Image not pushed to ACR — run the pipeline or `az acr build` manually

### Rate limit errors (`429 Too Many Requests`)

The default limit is `20/minute` per IP. Increase it in `.env`:

```ini
RATE_LIMIT=60/minute
```
