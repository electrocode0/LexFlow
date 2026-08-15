#LexFlow Architecture 

Client 
 |
 | HTTP 
🔽
FastAPI
 | 
 | SQL 
🔽
PostgreSQL 

Primary entities: 

- contract 
- documents
- clauses 
- reviews 
- audit_events 

Future processing pipeline: 

Contract 
 | 
🔽
Document Parsing 
 | 
🔽
LLM Extraction 
 |
🔽
RAG / Playbook Retrieval 
 | 
🔽
Deviation Analysis 
 | 
🔽
Human Review 