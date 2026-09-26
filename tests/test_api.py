import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql://lexflow:lexflow_dev@localhost:5432/lexflow"
)

from app.db import get_connection
from app.main import app
from app.chunking import chunk_text
from app.ingestion import ingest_document


@pytest.fixture(scope="session", autouse=True)
def database():
    try:
        with get_connection() as connection:
            connection.execute(Path("db/init.sql").read_text(encoding="utf-8"))
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL is unavailable: {exc}")


@pytest.fixture(autouse=True)
def clean_database(database):
    with get_connection() as connection:
        connection.execute(
            "TRUNCATE audit_events, clauses, documents, contracts CASCADE"
        )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_contract_lifecycle(client):
    response = client.post(
        "/contracts",
        json={
            "title": "Mutual NDA",
            "contract_type": "NDA",
            "counterparty": "Acme Legal",
        },
    )
    assert response.status_code == 201
    contract = response.json()
    contract_id = contract["id"]
    assert contract["status"] == "uploaded"

    assert client.get("/contracts").json()[0]["id"] == contract_id
    assert client.get(f"/contracts/{contract_id}").json()["title"] == "Mutual NDA"


def test_contract_validation_and_not_found(client):
    assert client.post("/contracts", json={"title": "   "}).status_code == 422
    assert (
        client.get("/contracts/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )


def test_document_upload_and_listing(client):
    contract_id = client.post("/contracts", json={"title": "NDA"}).json()["id"]
    response = client.post(
        f"/contracts/{contract_id}/documents",
        files={
            "file": (
                "nda.txt",
                b"Confidentiality survives termination.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    document = response.json()
    assert document["file_name"] == "nda.txt"
    assert document["raw_text"] == "Confidentiality survives termination."

    listed = client.get(f"/contracts/{contract_id}/documents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    with get_connection() as connection:
        chunk_count = connection.execute(
            "SELECT count(*) FROM document_chunks WHERE document_id = %s",
            (document["id"],),
        ).fetchone()["count"]
    assert chunk_count == 1


def test_document_validation_and_transaction_safety(client):
    missing_id = "00000000-0000-0000-0000-000000000000"
    response = client.post(
        f"/contracts/{missing_id}/documents",
        files={"file": ("nda.txt", b"text", "text/plain")},
    )
    assert response.status_code == 404
    assert client.post(
        f"/contracts/{missing_id}/documents",
        files={"file": ("nda.pdf", b"text", "application/pdf")},
    ).status_code == 415


def test_chunking_has_offsets_and_overlap():
    text = "Alpha clause.\n\nBeta clause.\n\nGamma clause."
    chunks = chunk_text(text, max_chars=25, overlap=5)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.text == text[chunk.start_offset : chunk.end_offset] for chunk in chunks)
    assert chunks[0].text == "Alpha clause."
    assert "Beta clause." in chunks[1].text
    assert all(chunk.text == text[chunk.start_offset : chunk.end_offset] for chunk in chunks)


def test_chunking_preserves_offsets_for_crlf_text():
    text = "First paragraph.\r\n\r\nSecond paragraph with a longer sentence."
    chunks = chunk_text(text, max_chars=30, overlap=5)
    assert all(chunk.text == text[chunk.start_offset : chunk.end_offset] for chunk in chunks)
    assert any("Second paragraph" in chunk.text for chunk in chunks)


def test_ingestion_rolls_back_when_embedding_fails(client):
    contract_id = client.post("/contracts", json={"title": "Rollback test"}).json()["id"]
    with pytest.raises(RuntimeError, match="embedding failed"):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO documents (contract_id, file_name, mime_type, raw_text)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (contract_id, "broken.txt", "text/plain", "Sensitive text"),
                )
                document_id = cursor.fetchone()["id"]

            class FailingProvider:
                dimension = 128

                def embed(self, text):
                    raise RuntimeError("embedding failed")

            ingest_document(connection, document_id, "Sensitive text", FailingProvider())

    with get_connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM documents WHERE file_name = 'broken.txt'"
        ).fetchone()["count"] == 0


def test_search_returns_sample_nda_supporting_passage(client):
    contract_id = client.post(
        "/contracts", json={"title": "Sample NDA", "contract_type": "NDA"}
    ).json()["id"]
    sample = Path("samples/sample_nda.txt").read_bytes()
    upload = client.post(
        f"/contracts/{contract_id}/documents",
        files={"file": ("sample_nda.txt", sample, "text/plain")},
    )
    assert upload.status_code == 201

    response = client.get(
        f"/contracts/{contract_id}/search",
        params={"q": "governing law Delaware", "limit": 3},
    )
    assert response.status_code == 200
    results = response.json()
    assert results
    assert "governed by the laws of Delaware" in results[0]["text"]
    assert results[0]["file_name"] == "sample_nda.txt"
    assert results[0]["contract_title"] == "Sample NDA"
    assert 0 <= results[0]["similarity"] <= 1


def test_search_validation_and_missing_contract(client):
    missing_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/contracts/{missing_id}/search", params={"q": "law"}).status_code == 404
    assert client.get(f"/contracts/{missing_id}/search", params={"q": " "}).status_code == 422