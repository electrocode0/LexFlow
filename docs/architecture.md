# LexFlow Architecture

React + TypeScript (Vite)
 |
 | HTTP / JSON / multipart
v
FastAPI
 |
 | upload transaction: raw text -> chunks -> embeddings
v
PostgreSQL + pgvector

Primary entities: 

- contract 
- documents
- clauses 
- reviews 
- audit_events 
- document_chunks

Retrieval pipeline:

Contract 
 | 
🔽
Document Upload
 |
v
Chunking + Embeddings
 |
v
Vector Retrieval
 |
v
Current: Query -> OpenAIEmbeddingProvider -> cosine search -> ranked source chunks

Ask API:
Question -> query embedding -> contract-scoped vector retrieval
		 -> LLMProvider -> structured answer + proposed chunk IDs
		 -> persisted-chunk citation validation -> answer + source citations

The `LLMProvider` boundary currently has an OpenAI implementation configured by
environment variables. It requests strict JSON output. Only retrieved chunk IDs and
text are included as document context; the API resolves every proposed citation to
the retrieved database rows and rejects unknown IDs. Prompt instructions require
the model to use only that context, treat document text as untrusted data, and say
when evidence is insufficient. Prompting is defense in depth, not a formal guarantee.

Future: Document Parsing -> LLM Extraction -> Deviation Analysis -> Human Review

The frontend owns presentation and transient form state only. It uses typed API
functions for contract creation/listing, document upload, and Q&A. Citation buttons
expand the exact citation text returned by the API and visually mark it as verified
source material; the frontend does not recreate or infer source passages.

The backend permits the configured local frontend origins through `CORS_ORIGINS`.
The Vite development server defaults to `http://127.0.0.1:5173`; set
`VITE_API_BASE_URL` when the API is hosted elsewhere.

`EmbeddingProvider` uses the production `OpenAIEmbeddingProvider` with the configured
`text-embedding-3-small` model and 1536-dimensional vectors. The schema dimension
must match provider output. Automated tests inject deterministic fake embedding and
LLM providers, so CI performs no paid model requests.

The versioned migration from vector(128) to vector(1536) deletes only derived chunks
and vectors. It preserves source documents, which `python -m app.reindex_embeddings`
uses to regenerate chunk rows and embeddings. New databases receive the current
dimension directly from `db/init.sql`.