# LexFlow

LexFlow is an AI-assisted contract intelligence and legal operations platform.

## Current milestone

The Day 1 backend foundation now includes a tested contract and document domain API:

- FastAPI backend with Pydantic request and response models
- PostgreSQL-backed contract and document persistence
- Contract creation, listing, and detail endpoints
- UTF-8 text document upload and listing endpoints
- Automatic paragraph-aware chunking with offsets
- Pluggable deterministic embedding provider
- pgvector persistence and cosine-similarity retrieval
- Contract-scoped source search with similarity scores and document metadata
- Grounded contract Q&A with verified source citations
- Vendor-independent LLM provider interface and OpenAI structured-output provider
- Transaction-safe database operations and database health monitoring
- Docker Compose development environment
- PostgreSQL schema initialized from `db/init.sql`
- Pytest integration coverage for the API and database behavior

Authentication and frontend work are intentionally deferred to later milestones.

## Architecture

FastAPI -> document ingestion -> PostgreSQL + pgvector

An upload stores the original UTF-8 text and synchronously creates paragraph-aware,
overlapping chunks. Each chunk stores source offsets and a vector from the configured
`EmbeddingProvider` abstraction. Search embeds the query and returns contract-scoped
source chunks ranked by cosine similarity. The current provider is deterministic and
local so the pipeline works without an external model; a hosted provider can replace it
without changing ingestion or retrieval.

`POST /contracts/{id}/ask` embeds the question, retrieves up to five chunks from
that contract, and sends only the question and those retrieved chunk IDs/text to
the configured LLM provider. The provider must return strict structured output
containing an answer and citation IDs. The API maps citations to the retrieved
database rows and rejects unknown IDs instead of returning model-invented sources.
Document text is untrusted data: the system prompt instructs the model never to
follow instructions found in a document and to report insufficient evidence rather
than use outside knowledge. This is a defense-in-depth boundary, not a guarantee
against every model error.

The production provider uses OpenAI's structured JSON output. The current local
hash embedding provider is deterministic token-overlap similarity, not a semantic
language embedding model.

## API endpoints

- `POST /contracts` creates a contract.
- `GET /contracts` lists contracts.
- `GET /contracts/{id}` returns one contract.
- `POST /contracts/{id}/documents` uploads a UTF-8 text document.
- `GET /contracts/{id}/documents` lists documents for a contract.
- `GET /contracts/{id}/search?q=...` retrieves ranked source chunks.
- `POST /contracts/{id}/ask` answers from retrieved contract chunks with citations.
- `GET /health` checks database connectivity.

## Development setup

Requirements: Docker Desktop and Python 3.12 or newer.

Create `.env` from `.env.example`. Set `OPENAI_API_KEY` to enable live Q&A; do not
commit `.env`. The deterministic tests use a fake LLM provider and need no API key.

The Compose database uses `pgvector/pgvector:pg16`. Recreate the volume after schema changes so the initialization script runs again.

Create a clean PostgreSQL volume and start the services:

```powershell
docker compose down -v
docker compose up -d --build
```

Install Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the API locally:

```powershell
uvicorn app.main:app --reload
```

Run the full test suite:

```powershell
pytest -q
```

API documentation: http://127.0.0.1:8000/docs