# LexFlow

LexFlow is an AI-assisted contract intelligence and legal operations platform.

## Current milestone

The Day 1 backend foundation now includes a tested contract and document domain API:

- FastAPI backend with Pydantic request and response models
- PostgreSQL-backed contract and document persistence
- Contract creation, listing, and detail endpoints
- UTF-8 text document upload and listing endpoints
- Transaction-safe database operations and database health monitoring
- Docker Compose development environment
- PostgreSQL schema initialized from `db/init.sql`
- Pytest integration coverage for the API and database behavior

RAG, embeddings, LLM integration, authentication, and frontend work are intentionally deferred to later milestones.

## Architecture

FastAPI -> PostgreSQL

The next processing milestone will extend the document path with parsing, chunking, embeddings, and retrieval.

## API endpoints

- `POST /contracts` creates a contract.
- `GET /contracts` lists contracts.
- `GET /contracts/{id}` returns one contract.
- `POST /contracts/{id}/documents` uploads a UTF-8 text document.
- `GET /contracts/{id}/documents` lists documents for a contract.
- `GET /health` checks database connectivity.

## Development setup

Requirements: Docker Desktop and Python 3.12 or newer.

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