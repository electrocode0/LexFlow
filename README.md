# LexFlow 

LexFlow is an AI-assisted contract intelligence and legal operations platform. 

## Status 

Currently under active development. 

### Day 1

- FastAPI backend 
- PostgreSQL database 
- Docker Compose development environment 
- initial legal data model
- database health monitoring 

## Architecture 

FatAPI -> PostgreSQL 

Future: 

Contract -> Parsing -> LLM Extraction -> RAG -> Policy Comparison 
-> Human Review -> Audit Trail 

## Development 

Start PostgreSQL: 

docker compose up -d

Start API: 

uvicorn app.main:app --reload

API documentation: 

http://127.0.0.1:8000/docs