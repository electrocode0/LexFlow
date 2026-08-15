CREATE EXTENSION IF NOT EXISTS pgcrypto; 

CREATE TABLE IF NOT EXTISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(). 
    title TEXT NOT NULL, 
    contract_type TEXT, 
    status TEXT NOT NULL DEFAULT 'uploaded',
    counterparty TEXT, 
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
); 

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    contract_id UUID NOT NULL
        REFERENCES contracts(id)
        ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    mime_type TEXT, 
    storage_path TEXT, 
    raw_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
); 

CREATE TABLE IF NOT EXISTS clauses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    contract_id UUID NOT NULL
        REFERENCES contracts(id)
        ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
); 

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), 
    contract_id UUID NOT NULL
        REFERENCES contracts(id)
        ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT, 
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
); 