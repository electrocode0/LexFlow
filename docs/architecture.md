# LexFlow Architecture

```text
React + TypeScript (Vite)
           |
      HTTP / JSON
           |
         FastAPI
           |
     LexFlow services
       /          \
LLMProvider   EmbeddingProvider
   /   \         /       \
Ollama OpenAI  Ollama   OpenAI
       \          /
     PostgreSQL + pgvector
```

LexFlow services depend on provider interfaces and factories, not provider-specific
clients. `LLM_PROVIDER` and `EMBEDDING_PROVIDER` are independently configurable.
Ollama is the local-development default; OpenAI is optional. A mixed setup is
supported in either direction: `LLM_PROVIDER=openai` with
`EMBEDDING_PROVIDER=ollama`, or `LLM_PROVIDER=ollama` with
`EMBEDDING_PROVIDER=openai`.

## Grounded Q&A

Document upload stores the original UTF-8 text and synchronously creates
paragraph-aware, overlapping chunks with source offsets. Each chunk receives an
embedding through `EmbeddingProvider`; query embeddings use the same configured
provider/model profile. Retrieval is contract-scoped and uses pgvector cosine
similarity.

The `/ask` service sends only the question and retrieved chunk IDs/text to
`LLMProvider.generate`. The validated structured response includes `answer`,
`answerable`, and proposed citation IDs. Providers implement a shared structured-output method.
OpenAI uses JSON Schema response formatting and Ollama uses `/api/chat` with the
Pydantic model's JSON Schema in `format`. LexFlow validates every returned result
with its Pydantic schema. The API resolves each cited ID against the retrieved
database rows and rejects unknown IDs before returning a citation. Document text
is treated as untrusted data in the prompt; this is defense in depth, not a formal
guarantee against every model error.

Provider-neutral instructions require direct evidence for every material claim,
explicit abstention when passages do not establish an answer, and prohibit
conflating agreement duration with termination rights. The API independently
normalizes unanswerable results to an abstention and requires at least one
verified citation that passes a conservative question-topic overlap check for
`answerable=true`. A narrow domain guard also forces an abstention for termination
questions unless retrieved text states a termination procedure. These lexical
checks are not a semantic entailment engine and may miss paraphrases: a valid
citation does not prove that it is relevant or that every answer claim is supported.
Ollama generation uses temperature zero to reduce variation during local evaluation.

## Provider configuration and diagnostics

Default local settings:

```dotenv
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.2:3b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_EMBEDDING_DIMENSION=768
```

OpenAI is optional and configured with `OPENAI_API_KEY`,
`OPENAI_LLM_MODEL`, and `OPENAI_EMBEDDING_MODEL`. OpenAI embedding output uses
768 dimensions to match the database schema. `AI_PROVIDER_TIMEOUT_SECONDS`
configures local-provider request timeouts; `OPENAI_TIMEOUT_SECONDS` remains
supported as an OpenAI-specific override.

`GET /health/ai` reports selected providers/models, embedding dimension, and
availability/model-install state without exposing credentials. Ollama model
unavailability reports the corresponding `ollama pull` command. `compose.yaml`
sets the backend's Ollama URL to `host.docker.internal` so a Docker Desktop
container can reach host-running Ollama. The host URL can be changed with
`OLLAMA_DOCKER_BASE_URL`; a backend run directly on the host uses
`http://localhost:11434`.

## Embedding compatibility and migration

`document_chunks.embedding` is fixed at `vector(768)`. `embedding_configuration`
records the single active embedding provider, model, and dimension. Ingestion and
retrieval reject profile changes, including switches between different same-sized
models. This prevents cosine comparisons across incompatible vector spaces.

To change embedding provider/model, explicitly rebuild all derived chunks and
vectors by running `python -m app.reindex_embeddings` (or through the backend
container). Reindexing reads preserved `documents.raw_text`, deletes old chunks,
stores the selected profile, and recreates vectors in one transaction. It creates
new chunk IDs; contracts, documents, and source text are preserved.

Existing databases on `vector(1536)` must first apply
`db/migrations/003_embedding_provider_profile.sql`. That migration removes the
old chunks/vectors, changes the column to `vector(768)`, and creates the profile
table. Then reindex documents with the selected embedding provider. Fresh databases
use the current `db/init.sql` schema directly. The older
`002_semantic_embeddings.sql` migration is only for databases that still use
`vector(128)`.


The fixture at `tests/fixtures/grounded_qa_cases.json` stores answerability and
concept expectations rather than exact target prose. The live comparison utility
resolves `sample_nda.txt` in the selected contract and ranks only that document's
chunks. This evaluation-only document filter prevents unrelated contract
documents from affecting benchmark context; production retrieval remains scoped
to the contract as a whole. The utility records retrieval ranks, similarity,
offsets, evidence coverage, supported concept accuracy, abstention, citation
relevance/source matching, structured-output success, and latency. These
measures help separate retrieval misses from generation failures but do not
prove legal correctness.

## Frontend

The React frontend owns presentation and transient form state. It consumes typed
API functions for contracts, uploads, and grounded Q&A. Citation controls expand
the exact source text returned by the API; the frontend does not infer, retrieve,
or validate source passages.
