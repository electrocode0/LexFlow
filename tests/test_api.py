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