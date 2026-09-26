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

Future: Retrieval -> LLM -> structured answer -> citations
	Document Parsing -> LLM Extraction -> Deviation Analysis -> Human Review

`EmbeddingProvider` is the boundary for replacing the deterministic local
`HashEmbeddingProvider` with a model-backed implementation in a later milestone.