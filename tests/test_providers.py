import json

import httpx
import pytest

import app.embeddings as embeddings
import app.llm as llm
from app.embeddings import (
    EmbeddingProviderError,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    UnconfiguredEmbeddingProvider,
)
from app.llm import (
    LLMAnswer,
    LLMProviderError,
    LLMTimeoutError,
    OllamaLLMProvider,
    OpenAILLMProvider,
    RetrievedChunk,
    UnconfiguredLLMProvider,
)


def ollama_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_factories_default_to_ollama_without_openai_key(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", None)
    monkeypatch.setattr(embeddings, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(embeddings, "OPENAI_API_KEY", None)

    assert isinstance(llm.get_llm_provider(), OllamaLLMProvider)
    assert isinstance(embeddings.get_embedding_provider(), OllamaEmbeddingProvider)


def test_factories_select_openai_providers(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(embeddings, "OPENAI_API_KEY", "test-key")

    assert isinstance(llm.get_llm_provider(), OpenAILLMProvider)
    assert isinstance(embeddings.get_embedding_provider(), OpenAIEmbeddingProvider)


def test_openai_selection_without_a_key_fails_when_used(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", None)
    monkeypatch.setattr(embeddings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(embeddings, "OPENAI_API_KEY", None)

    llm_provider = llm.get_llm_provider()
    embedding_provider = embeddings.get_embedding_provider()
    assert isinstance(llm_provider, UnconfiguredLLMProvider)
    assert isinstance(embedding_provider, UnconfiguredEmbeddingProvider)
    with pytest.raises(llm.LLMNotConfiguredError, match="OPENAI_API_KEY"):
        llm_provider.generate("question", [])
    with pytest.raises(embeddings.EmbeddingNotConfiguredError, match="OPENAI_API_KEY"):
        embedding_provider.embed("text")


@pytest.mark.parametrize(
    ("factory", "setting", "invalid_value"),
    [
        (llm.get_llm_provider, "LLM_PROVIDER", "local"),
        (embeddings.get_embedding_provider, "EMBEDDING_PROVIDER", "local"),
    ],
)
def test_factories_reject_unknown_provider(monkeypatch, factory, setting, invalid_value):
    module = llm if setting == "LLM_PROVIDER" else embeddings
    monkeypatch.setattr(module, setting, invalid_value)
    with pytest.raises(ValueError, match=setting):
        factory()


def test_ollama_llm_requests_and_validates_structured_output():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "answer": "The term is one year.",
                            "answerable": True,
                            "citation_ids": [],
                        }
                    )
                }
            },
        )

    provider = OllamaLLMProvider(
        "http://ollama", "llama3.2:3b", client=ollama_client(handler)
    )
    result = provider.generate("What is the term?", [])

    assert isinstance(result, LLMAnswer)
    assert result.answer == "The term is one year."
    assert requests[0]["model"] == "llama3.2:3b"
    assert requests[0]["stream"] is False
    assert requests[0]["options"] == {"temperature": 0}
    assert requests[0]["format"] == LLMAnswer.model_json_schema()


def test_ollama_llm_rejects_malformed_structured_output():
    provider = OllamaLLMProvider(
        "http://ollama",
        "llama3.2:3b",
        client=ollama_client(
            lambda request: httpx.Response(
                200,
                json={
                    "message": {
                        "content": (
                            '{"answer": "", "answerable": true, '
                            '"citation_ids": "bad"}'
                        )
                    }
                },
            )
        ),
    )
    with pytest.raises(LLMProviderError, match="invalid structured output"):
        provider.generate("question", [])


def test_ollama_llm_reports_unavailable_model_with_pull_command():
    provider = OllamaLLMProvider(
        "http://ollama",
        "missing-model",
        client=ollama_client(
            lambda request: httpx.Response(
                404, json={"error": "model 'missing-model' not found"}
            )
        ),
    )
    with pytest.raises(LLMProviderError, match="ollama pull missing-model"):
        provider.generate("question", [])


def test_ollama_llm_reports_connection_failure():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaLLMProvider(
        "http://ollama", "llama3.2:3b", client=ollama_client(handler)
    )
    with pytest.raises(LLMProviderError, match="Could not connect to Ollama"):
        provider.generate("question", [])


def test_ollama_llm_maps_timeouts():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OllamaLLMProvider(
        "http://ollama", "llama3.2:3b", client=ollama_client(handler)
    )
    with pytest.raises(LLMTimeoutError):
        provider.generate("question", [])


def test_ollama_embedding_detects_dimension_and_generates_vector():
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(
                200, json={"model_info": {"nomic-bert.embedding_length": 768}}
            )
        return httpx.Response(200, json={"embeddings": [[0.25] * 768]})

    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "nomic-embed-text",
        expected_dimension=768,
        client=ollama_client(handler),
    )

    assert provider.dimension == 768
    assert len(provider.embed("contract clause")) == 768


def test_ollama_embedding_rejects_dimension_mismatch():
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(
                200, json={"model_info": {"nomic-bert.embedding_length": 768}}
            )
        return httpx.Response(200, json={"embeddings": [[0.25] * 3]})

    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "nomic-embed-text",
        expected_dimension=768,
        client=ollama_client(handler),
    )
    with pytest.raises(EmbeddingProviderError, match="Expected 768-dimensional"):
        provider.embed("contract clause")


def test_ollama_embedding_rejects_configured_dimension_mismatch():
    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "nomic-embed-text",
        expected_dimension=1536,
        client=ollama_client(
            lambda request: httpx.Response(
                200, json={"model_info": {"nomic-bert.embedding_length": 768}}
            )
        ),
    )
    with pytest.raises(EmbeddingProviderError, match="reports 768 dimensions"):
        _ = provider.dimension


def test_ollama_embedding_reports_missing_model():
    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "missing-model",
        expected_dimension=768,
        client=ollama_client(
            lambda request: httpx.Response(
                404, json={"error": "model 'missing-model' not found"}
            )
        ),
    )
    with pytest.raises(EmbeddingProviderError, match="ollama pull missing-model"):
        _ = provider.dimension


def test_ollama_embedding_reports_server_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "nomic-embed-text",
        expected_dimension=768,
        client=ollama_client(handler),
    )
    with pytest.raises(EmbeddingProviderError, match="Could not connect to Ollama"):
        _ = provider.dimension


def test_ollama_embedding_rejects_malformed_response():
    provider = OllamaEmbeddingProvider(
        "http://ollama",
        "nomic-embed-text",
        expected_dimension=768,
        client=ollama_client(lambda request: httpx.Response(200, content=b"not json")),
    )
    with pytest.raises(EmbeddingProviderError, match="malformed JSON"):
        _ = provider.dimension


def test_citation_ids_stay_in_provider_neutral_answer_schema():
    chunk = RetrievedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001",
        text="The term is one year.",
    )
    assert str(chunk.chunk_id) == "00000000-0000-0000-0000-000000000001"


def test_answerability_must_be_a_boolean():
    with pytest.raises(ValueError):
        LLMAnswer.model_validate(
            {
                "answer": "Maybe.",
                "answerable": "yes",
                "citation_ids": [],
            }
        )


def test_citation_ids_must_be_uuid_values():
    with pytest.raises(ValueError):
        LLMAnswer.model_validate(
            {
                "answer": "Supported answer.",
                "answerable": True,
                "citation_ids": ["chunk-a"],
            }
        )
