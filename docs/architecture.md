# LexFlow Architecture

Client
 |
 | HTTP
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
Current: Query -> HashEmbeddingProvider -> cosine search -> ranked source chunks

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

`EmbeddingProvider` is the boundary for replacing the deterministic local
`HashEmbeddingProvider` with a model-backed implementation in a later milestone.