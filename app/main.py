from uuid import UUID

import psycopg
from fastapi import FastAPI, File, HTTPException, UploadFile, status

from app.db import get_connection
from app.embeddings import embedding_provider
from app.ingestion import ingest_document, vector_literal
from app.models import (
    ContractCreate,
    ContractResponse,
    DocumentResponse,
    SearchResult,
)

app = FastAPI(
    title="LexFlow API",
    version="0.1.0",
    description="API for LexFlow, a contract intelligence platform.",
)

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
SUPPORTED_DOCUMENT_TYPES = {"text/plain", "application/octet-stream"}


def database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )

@app.get("/")
def root():
    return {"name": "LexFlow", "status": "running"}


@app.post(
    "/contracts",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_contract(contract: ContractCreate):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO contracts (title, contract_type, counterparty)
                    VALUES (%s, %s, %s)
                    RETURNING id, title, contract_type, status, counterparty,
                              created_at, updated_at
                    """,
                    (contract.title.strip(), contract.contract_type, contract.counterparty),
                )
                return cur.fetchone()
    except psycopg.Error as exc:
        raise database_error() from exc


@app.get("/contracts", response_model=list[ContractResponse])
def list_contracts():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, contract_type, status, counterparty,
                           created_at, updated_at
                    FROM contracts
                    ORDER BY created_at DESC
                    """
                )
                return cur.fetchall()
    except psycopg.Error as exc:
        raise database_error() from exc


@app.get("/contracts/{contract_id}/search", response_model=list[SearchResult])
def search_contract(contract_id: UUID, q: str, limit: int = 5):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query must not be blank.")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 50.")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                query_vector = vector_literal(embedding_provider.embed(query))
                cur.execute("SELECT 1 FROM contracts WHERE id = %s", (contract_id,))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Contract not found.")
                cur.execute(
                    """
                          SELECT dc.id AS chunk_id, dc.document_id, d.file_name, d.mime_type,
                              c.title AS contract_title, c.contract_type,
                           dc.chunk_index, dc.text, dc.start_offset, dc.end_offset,
                           1 - (dc.embedding <=> %s::vector) AS similarity
                    FROM document_chunks AS dc
                    JOIN documents AS d ON d.id = dc.document_id
                          JOIN contracts AS c ON c.id = d.contract_id
                          WHERE d.contract_id = %s
                    ORDER BY dc.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        query_vector,
                        contract_id,
                        query_vector,
                        limit,
                    ),
                )
                return cur.fetchall()
    except psycopg.Error as exc:
        raise database_error() from exc


@app.get("/contracts/{contract_id}", response_model=ContractResponse)
def get_contract(contract_id: UUID):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, contract_type, status, counterparty,
                           created_at, updated_at
                    FROM contracts
                    WHERE id = %s
                    """,
                    (contract_id,),
                )
                contract = cur.fetchone()
                if contract is None:
                    raise HTTPException(status_code=404, detail="Contract not found.")
                return contract
    except psycopg.Error as exc:
        raise database_error() from exc


@app.post(
    "/contracts/{contract_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(contract_id: UUID, file: UploadFile = File(...)):
    if file.content_type not in SUPPORTED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only UTF-8 text documents are supported.",
        )
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="A file name is required.")

    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 10 MB limit.")
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Document must be valid UTF-8 text.",
        ) from exc

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM contracts WHERE id = %s", (contract_id,))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Contract not found.")
                cur.execute(
                    """
                    INSERT INTO documents (contract_id, file_name, mime_type, raw_text)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, contract_id, file_name, mime_type, storage_path,
                              raw_text, created_at
                    """,
                    (contract_id, file.filename.strip(), file.content_type, raw_text),
                )
                document = cur.fetchone()
                ingest_document(conn, document["id"], raw_text, embedding_provider)
                return document
    except psycopg.Error as exc:
        raise database_error() from exc


@app.get("/contracts/{contract_id}/documents", response_model=list[DocumentResponse])
def list_documents(contract_id: UUID):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM contracts WHERE id = %s", (contract_id,))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Contract not found.")
                cur.execute(
                    """
                    SELECT id, contract_id, file_name, mime_type, storage_path,
                           raw_text, created_at
                    FROM documents
                    WHERE contract_id = %s
                    ORDER BY created_at DESC
                    """,
                    (contract_id,),
                )
                return cur.fetchall()
    except psycopg.Error as exc:
        raise database_error() from exc


@app.get("/health")
def health():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "healthy", "database": "connected"}
    except psycopg.Error:
        return {"status": "degraded", "database": "disconnected"}