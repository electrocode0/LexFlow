from uuid import UUID

from psycopg import Connection

from app.embeddings import embedding_provider
from app.ingestion import vector_literal


class ContractNotFoundError(Exception):
    pass


def retrieve_contract_chunks(
    connection: Connection,
    contract_id: UUID,
    query: str,
    limit: int = 5,
) -> list[dict]:
    query_vector = vector_literal(embedding_provider.embed(query))
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM contracts WHERE id = %s", (contract_id,))
        if cursor.fetchone() is None:
            raise ContractNotFoundError

        cursor.execute(
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
            (query_vector, contract_id, query_vector, limit),
        )
        return cursor.fetchall()