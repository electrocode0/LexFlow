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

    IF current_embedding_type IS DISTINCT FROM 'vector(128)' THEN
        RAISE EXCEPTION 'Expected document_chunks.embedding vector(128), got %',
            current_embedding_type;
    END IF;
END;
$$;

DROP INDEX IF EXISTS document_chunks_embedding_idx;

-- Embeddings and chunks are derived from the preserved documents.raw_text.
DELETE FROM document_chunks;

ALTER TABLE document_chunks DROP COLUMN embedding;
ALTER TABLE document_chunks ADD COLUMN embedding vector(1536) NOT NULL;

CREATE INDEX document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

COMMIT;