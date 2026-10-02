from uuid import UUID

import psycopg
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.config import CORS_ORIGINS
from app.db import get_connection
from app.embeddings import (
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    embedding_provider,
)
from app.ingestion import ingest_document, vector_literal
from app.llm import (
    LLMAnswer,
    LLMNotConfiguredError,
    LLMProviderError,
    LLMTimeoutError,
    RetrievedChunk,
    llm_provider,
)
from app.models import (
    AskRequest,
    AskResponse,
    ContractCreate,
    ContractResponse,
    DocumentResponse,
    SearchResult,
)
from app.retrieval import ContractNotFoundError, retrieve_contract_chunks

app = FastAPI(
    title="LexFlow API",
    version="0.1.0",
    description="API for LexFlow, a contract intelligence platform.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
SUPPORTED_DOCUMENT_TYPES = {"text/plain", "application/octet-stream"}


def database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )


def embedding_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmbeddingNotConfiguredError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic embedding provider is not configured.",
        )
    if isinstance(exc, EmbeddingTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Semantic embedding request timed out.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Semantic embedding request failed.",
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
            return retrieve_contract_chunks(conn, contract_id, query, limit)
    except ContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Contract not found.") from exc
    except (EmbeddingNotConfiguredError, EmbeddingTimeoutError, EmbeddingProviderError) as exc:
        raise embedding_error(exc) from exc
    except psycopg.Error as exc:
        raise database_error() from exc


@app.post("/contracts/{contract_id}/ask", response_model=AskResponse)
def ask_contract(contract_id: UUID, request: AskRequest):
    try:
        with get_connection() as conn:
            chunks = retrieve_contract_chunks(
                conn, contract_id, request.question, limit=5
            )
    except ContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Contract not found.") from exc
    except (EmbeddingNotConfiguredError, EmbeddingTimeoutError, EmbeddingProviderError) as exc:
        raise embedding_error(exc) from exc
    except psycopg.Error as exc:
        raise database_error() from exc

    context = [
        RetrievedChunk(chunk_id=chunk["chunk_id"], text=chunk["text"])
        for chunk in chunks
    ]
    try:
        answer = LLMAnswer.model_validate(
            llm_provider.generate(request.question, context)
        )
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Language model provider is not configured.",
        ) from exc
    except (LLMTimeoutError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Language model request timed out.",
        ) from exc
    except (LLMProviderError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Language model returned an invalid response.",
        ) from exc

    chunks_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    citations = []
    for citation_id in answer.citation_ids:
        try:
            normalized_id = str(UUID(citation_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Language model cited an unknown source.",
            ) from exc
        chunk = chunks_by_id.get(normalized_id)
        if chunk is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Language model cited an unknown source.",
            )
        citations.append(
            {
                "document_id": chunk["document_id"],
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
            }
        )
    return AskResponse(answer=answer.answer, citations=citations)


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
    except (EmbeddingNotConfiguredError, EmbeddingTimeoutError, EmbeddingProviderError) as exc:
        raise embedding_error(exc) from exc


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
    except (EmbeddingNotConfiguredError, EmbeddingTimeoutError, EmbeddingProviderError) as exc:
        raise embedding_error(exc) from exc
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