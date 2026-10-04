BEGIN;

DO $$
DECLARE
    current_embedding_type TEXT;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
    INTO current_embedding_type
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = 'document_chunks'::regclass
      AND attribute.attname = 'embedding';

    IF current_embedding_type = 'vector(1536)' THEN
        DROP INDEX IF EXISTS document_chunks_embedding_idx;
        DELETE FROM document_chunks;
        ALTER TABLE document_chunks
            ALTER COLUMN embedding TYPE vector(768);
        CREATE INDEX document_chunks_embedding_idx
            ON document_chunks USING hnsw (embedding vector_cosine_ops);
    ELSIF current_embedding_type IS DISTINCT FROM 'vector(768)' THEN
        RAISE EXCEPTION 'Expected document_chunks.embedding vector(1536) or vector(768), got %',
            current_embedding_type;
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS embedding_configuration (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    provider_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
