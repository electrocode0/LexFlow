# LexFlow

LexFlow is an AI-assisted contract intelligence and legal operations platform.

## Current milestone

The backend includes a tested contract and document domain API:

- FastAPI backend with Pydantic request and response models
- PostgreSQL-backed contract and document persistence
- Contract creation, listing, and detail endpoints
- UTF-8 text document upload and listing endpoints
- Automatic paragraph-aware chunking with offsets
- Provider-neutral LLM and embedding interfaces with Ollama and OpenAI implementations
- Ollama local chat and embeddings as the default, with no API key required
- OpenAI as an optional hosted provider; LLM and embedding providers can be mixed
- pgvector persistence and cosine-similarity retrieval
- Contract-scoped source search with similarity scores and document metadata
- Grounded contract Q&A with verified source citations
- Explicit answerability in grounded Q&A, with conservative abstention for unsupported answers
- Structured LLM output validated by Pydantic before it reaches LexFlow services
- AI provider health diagnostics that report provider/model availability without secrets
- React and TypeScript contract dashboard and workspace
- Click-through source citations with highlighted backend-returned passages
- Transaction-safe database operations and database health monitoring
- Docker Compose development environment
- PostgreSQL schema initialized from `db/init.sql`
- Pytest integration coverage for the API and database behavior

Authentication is intentionally deferred to a later milestone.

## Architecture

FastAPI -> provider interfaces -> Ollama (default) or OpenAI (optional)
        -> document ingestion -> PostgreSQL + pgvector

An upload stores the original UTF-8 text and synchronously creates paragraph-aware,
overlapping chunks. Each chunk stores source offsets and a 768-dimensional vector
from the configured `EmbeddingProvider` abstraction. Ollama's default
`nomic-embed-text` model reports a 768-dimensional embedding. OpenAI
`text-embedding-3-small` is configured to return 768 dimensions as well. Query and
document vectors must use the same provider/model profile.

`POST /contracts/{id}/ask` embeds the question, retrieves up to five chunks from
that contract, and sends only the question and those retrieved chunk IDs/text to
the configured LLM provider. The provider must return strict structured output
containing an answer and citation IDs. The API maps citations to the retrieved
database rows and rejects unknown IDs instead of returning model-invented sources.
The response includes `answerable`; an absent citation set is downgraded to an
abstention, and termination questions are not answered from term-duration text
unless the supplied passages state a termination procedure. Valid citations alone
do not prove that an answer is correct.
Document text is untrusted data: the system prompt instructs the model never to
follow instructions found in a document and to report insufficient evidence rather
than use outside knowledge. This is a defense-in-depth boundary, not a guarantee
against every model error.

Both providers implement the same structured-output contract. OpenAI uses strict
JSON Schema responses; Ollama uses its local chat API's JSON Schema `format`.
LexFlow validates the returned JSON against the requested Pydantic model, then
validates citations against retrieved database rows. Provider-specific errors
(including a missing Ollama model) are surfaced as actionable API errors rather than
being replaced with fabricated answers. Automated tests use deterministic fake
providers and mocked Ollama HTTP responses; they do not make paid or live-model
requests.

The `embedding_configuration` row records the active provider, model, and vector
dimension. Upload and retrieval reject a different profile, even when its vector
dimension happens to match. Reindexing is an explicit, transactional operation that
deletes and rebuilds derived chunks/vectors from preserved `documents.raw_text`.
Changing embedding provider/model requires reindexing; it creates new chunk IDs.

For an existing database using the earlier `vector(1536)` schema, migrate once and
rebuild the derived chunks:

```powershell
docker compose stop backend
Get-Content -Raw db/migrations/003_embedding_provider_profile.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U lexflow -d lexflow
docker compose up -d --build backend
docker compose exec backend python -m app.reindex_embeddings
```

The migration removes incompatible vectors/chunks and preserves contracts,
documents, and original source text. Fresh databases get the current dimension and
profile table from `db/init.sql` and do not need this migration.
Databases still on `vector(128)` must first apply
`db/migrations/002_semantic_embeddings.sql`, then apply migration 003 above.
For existing documents, install/pull the selected embedding model and confirm it
is available before reindexing; otherwise the reindex transaction will fail and
roll back.

The React frontend consumes the API directly. It creates and opens contracts,
uploads `.txt` files, submits questions, and expands citations using the exact
source text returned by the backend. It does not implement ingestion, retrieval,
or citation validation itself.

## API endpoints

- `POST /contracts` creates a contract.
- `GET /contracts` lists contracts.
- `GET /contracts/{id}` returns one contract.
- `POST /contracts/{id}/documents` uploads a UTF-8 text document.
- `GET /contracts/{id}/documents` lists documents for a contract.
- `GET /contracts/{id}/search?q=...` retrieves ranked source chunks.
- `POST /contracts/{id}/ask` answers from retrieved contract chunks with citations.
- `GET /health` checks database connectivity.
- `GET /health/ai` reports selected providers/models, embedding dimension, and model
  availability without exposing credentials.

## Development setup

Requirements: Docker Desktop and Python 3.12 or newer.
The frontend requires Node.js 20.19 or newer and npm.

### OLLAMA — DEFAULT / FREE LOCAL DEVELOPMENT

Install Ollama for Windows from <https://ollama.com/download>, then pull the
configured models from PowerShell:

```powershell
ollama pull llama3.2:3b
ollama pull nomic-embed-text
ollama list
```

Ollama must be running on the host. For a backend started directly on Windows,
`OLLAMA_BASE_URL=http://localhost:11434` is the default. The Compose backend uses
`http://host.docker.internal:11434` to reach Ollama on the Docker Desktop host; set
`OLLAMA_DOCKER_BASE_URL` if your Docker setup requires a different host address.
The backend does not start or manage Ollama.

### OPENAI — OPTIONAL HOSTED PROVIDER

Create `.env` from `.env.example`. OpenAI is optional: only set `OPENAI_API_KEY`
when selecting an OpenAI provider. Never commit `.env`. Providers are selected
independently, so mixed configurations are supported:

```dotenv
# Local (default)
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama

# Hosted
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your-key

# Mixed
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=ollama

# Mixed (reverse)
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your-key
```

Automated tests use fakes/mocks and need neither Ollama nor an API key.
The default CORS allowlist includes the local Vite origins at `localhost:5173` and
`127.0.0.1:5173`.

The Compose database uses `pgvector/pgvector:pg16`. Fresh databases initialize
from `db/init.sql`; existing volumes need the migration above when moving from the
previous 1536-dimensional schema.

Start the services (this preserves existing database volumes):

```powershell
docker compose up -d --build
```

Check provider/model status at <http://127.0.0.1:8000/health/ai>. The frontend is
not required for the provider smoke test; Swagger UI is available at
<http://127.0.0.1:8000/docs>.

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

Run the frontend in a second terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open http://127.0.0.1:5173. Set `VITE_API_BASE_URL` in `frontend/.env.local` to
change the API origin. Frontend checks:

```powershell
npm run lint
npm run typecheck
npm run build
```

Run the full test suite:

```powershell
$env:DATABASE_URL = "postgresql://lexflow:lexflow_dev@localhost:5432/lexflow_test"
docker compose exec postgres psql -U lexflow -d postgres -c "CREATE DATABASE lexflow_test"
pytest -q
```

The API test fixture refuses to truncate a database whose name does not end in
`_test`. The development database is not a test database.

API documentation: http://127.0.0.1:8000/docs

### Grounded-Q&A evaluation

The deterministic evaluation cases live in
`tests/fixtures/grounded_qa_cases.json`. They grade concepts and answerability,
not exact prose. The live evaluation resolves `sample_nda.txt` within the chosen
contract and retrieves only that document's chunks; other documents attached to
the contract cannot affect benchmark context. This evaluation-only filter does
not change production retrieval, which remains contract-scoped. To evaluate local
Ollama models (after database migration/reindexing), run:

```powershell
python -m scripts.evaluate_grounded_qa --contract-id <contract-uuid>
```

The default comparison uses `llama3.2:3b`, `phi:latest`, and `mistral:latest`;
all use the configured embedding model and the same NDA-only retrieved chunks. The report
includes retrieval ranking/similarity/source offsets, passage coverage, answer
concept coverage, answerability and abstention scores, citation relevance and
source-offset checks, structured-output success, and latency. Evaluation is
diagnostic and does not establish production legal reliability.

### Manual Ollama smoke test

After installing Ollama and pulling the models above:

1. Start PostgreSQL and LexFlow with `docker compose up -d --build` (or start
   PostgreSQL with Compose and run `uvicorn app.main:app --reload` in the local
   virtual environment).
2. Open `/health/ai` and confirm the selected Ollama models are available.
3. Create a contract:

   ```powershell
   $contract = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/contracts -ContentType 'application/json' -Body '{"title":"Sample NDA"}'
   $contractId = $contract.id
   ```

4. Upload the included test agreement:

   ```powershell
   curl.exe -s -X POST "http://127.0.0.1:8000/contracts/$contractId/documents" -F "file=@samples/sample_nda.txt;type=text/plain"
   ```

   Upload synchronously creates chunks and embeddings. Confirm the response is
   successful and inspect the stored source at
   `GET /contracts/{contractId}/documents`.
5. Run contract-scoped retrieval:

   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/contracts/$contractId/search?q=confidentiality%20obligations"
   ```

6. Ask a grounded question:

   ```powershell
   $answer = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/contracts/$contractId/ask" -ContentType 'application/json' -Body '{"question":"What confidentiality obligations does the agreement impose?"}'
   $answer | ConvertTo-Json -Depth 8
   ```

7. Verify each returned `citations[].text` against the uploaded document returned
   from `GET /contracts/{contractId}/documents`. The API resolves citation IDs to
   persisted retrieved chunks; it rejects IDs that were not retrieved. Do not treat
   this manual smoke test as passed until the requests have been run against your
   local Ollama installation.

If embeddings are switched after uploading documents, run
`python -m app.reindex_embeddings` from the local environment, or
`docker compose exec backend python -m app.reindex_embeddings` for the Compose
backend, before searching. The database rejects use of vectors associated with a
different provider/model profile.