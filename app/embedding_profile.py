from psycopg import Connection

from app.embeddings import EmbeddingConfigurationMismatchError, EmbeddingProvider


def lock_embedding_profile(connection: Connection) -> None:
    connection.execute("SELECT pg_advisory_xact_lock(593002914)")


def _profile(provider: EmbeddingProvider) -> tuple[str, str, int]:
    return provider.provider_name, provider.model_name, provider.dimension


def register_embedding_profile(
    connection: Connection, provider: EmbeddingProvider
) -> None:
    lock_embedding_profile(connection)
    provider_name, model_name, dimension = _profile(provider)
    connection.execute(
        """
        INSERT INTO embedding_configuration (id, provider_name, model_name, dimension)
        VALUES (1, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET provider_name = EXCLUDED.provider_name,
            model_name = EXCLUDED.model_name,
            dimension = EXCLUDED.dimension,
            updated_at = NOW()
        """,
        (provider_name, model_name, dimension),
    )


def ensure_embedding_profile(
    connection: Connection, provider: EmbeddingProvider
) -> None:
    lock_embedding_profile(connection)
    provider_name, model_name, dimension = _profile(provider)
    row = connection.execute(
        """
        SELECT provider_name, model_name, dimension
        FROM embedding_configuration
        WHERE id = 1
        FOR UPDATE
        """
    ).fetchone()
    if row is None:
        chunk_count = connection.execute(
            "SELECT count(*) AS count FROM document_chunks"
        ).fetchone()["count"]
        if chunk_count:
            raise EmbeddingConfigurationMismatchError(
                "Stored vectors have no recorded embedding profile. "
                "Rebuild them with `python -m app.reindex_embeddings`."
            )
        register_embedding_profile(connection, provider)
        return

    stored = (row["provider_name"], row["model_name"], row["dimension"])
    requested = (provider_name, model_name, dimension)
    if stored != requested:
        raise EmbeddingConfigurationMismatchError(
            "The configured embedding provider/model/dimension does not match the "
            "vectors in this database. Rebuild them with "
            "`python -m app.reindex_embeddings` before ingesting or searching."
        )
