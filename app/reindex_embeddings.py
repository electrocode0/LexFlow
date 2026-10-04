from app.db import get_connection
from app.embedding_profile import lock_embedding_profile, register_embedding_profile
from app.embeddings import embedding_provider
from app.ingestion import ingest_document


def reindex_documents() -> tuple[int, int]:
    with get_connection() as connection:
        lock_embedding_profile(connection)
        documents = connection.execute(
            "SELECT id, raw_text FROM documents ORDER BY created_at, id"
        ).fetchall()
        connection.execute("DELETE FROM document_chunks")
        register_embedding_profile(connection, embedding_provider)

        document_count = 0
        chunk_count = 0
        for document in documents:
            if document["raw_text"] is None:
                continue
            chunk_count += ingest_document(
                connection,
                document["id"],
                document["raw_text"],
                embedding_provider,
            )
            document_count += 1
    return document_count, chunk_count


if __name__ == "__main__":
    documents, chunks = reindex_documents()
    print(f"Re-embedded {chunks} chunks across {documents} documents.")