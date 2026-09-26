from uuid import UUID

from psycopg import Connection

from app.chunking import chunk_text
from app.embeddings import EmbeddingProvider


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def ingest_document(
    connection: Connection,
    document_id: UUID,
    raw_text: str,
    embedding_provider: EmbeddingProvider,
) -> int:
    chunks = chunk_text(raw_text)
    with connection.cursor() as cursor:
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks
                    (document_id, chunk_index, text, start_offset, end_offset, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    document_id,
                    chunk.index,
                    chunk.text,
                    chunk.start_offset,
                    chunk.end_offset,
                    vector_literal(embedding_provider.embed(chunk.text)),
                ),
            )
    return len(chunks)