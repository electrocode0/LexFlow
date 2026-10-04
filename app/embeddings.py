import math
from typing import Any, Protocol

import httpx
from openai import APITimeoutError, OpenAI, OpenAIError

from app.config import (
    AI_PROVIDER_TIMEOUT_SECONDS,
    EMBEDDING_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_EMBEDDING_DIMENSION,
    OLLAMA_EMBEDDING_MODEL,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_DIMENSION,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    @property
    def dimension(self) -> int:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def check_available(self) -> dict[str, Any]:
        ...


class EmbeddingError(Exception):
    pass


class EmbeddingNotConfiguredError(EmbeddingError):
    pass


class EmbeddingTimeoutError(EmbeddingError):
    pass


class EmbeddingProviderError(EmbeddingError):
    pass


class EmbeddingConfigurationMismatchError(EmbeddingProviderError):
    pass


def _validated_vector(values: Any, expected_dimension: int) -> list[float]:
    if not isinstance(values, list) or len(values) != expected_dimension:
        actual = len(values) if isinstance(values, list) else "unknown"
        raise EmbeddingProviderError(
            f"Expected {expected_dimension}-dimensional embeddings, got {actual}."
        )
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise EmbeddingProviderError(
            "The embedding provider returned a non-numeric vector."
        ) from exc
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingProviderError(
            "The embedding provider returned non-finite vector values."
        )
    return vector


class OpenAIEmbeddingProvider:
    provider_name = "openai"
    dimension = OPENAI_EMBEDDING_DIMENSION

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        if not model.startswith("text-embedding-3-"):
            raise ValueError(
                "The configured embedding model must support the dimensions parameter."
            )
        self.model_name = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout_seconds)

    def embed(self, text: str) -> list[float]:
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text,
                dimensions=self.dimension,
            )
        except APITimeoutError as exc:
            raise EmbeddingTimeoutError("The OpenAI embedding request timed out.") from exc
        except OpenAIError as exc:
            raise EmbeddingProviderError("The OpenAI embedding request failed.") from exc

        if not response.data:
            raise EmbeddingProviderError("The OpenAI provider returned no vector.")
        return _validated_vector(response.data[0].embedding, self.dimension)

    def check_available(self) -> dict[str, Any]:
        try:
            self.client.models.retrieve(self.model_name, timeout=5)
        except APITimeoutError:
            return {"available": False, "model_available": False, "error": "Request timed out."}
        except OpenAIError:
            return {
                "available": False,
                "model_available": False,
                "error": "OpenAI is unavailable or the configured model is inaccessible.",
            }
        return {"available": True, "model_available": True, "error": None}


class OllamaEmbeddingProvider:
    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = AI_PROVIDER_TIMEOUT_SECONDS,
        expected_dimension: int | None = None,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.expected_dimension = expected_dimension
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = self._discover_dimension()
        return self._dimension

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = getattr(self.client, method)(
                f"{self.base_url}{path}", **kwargs
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError("The Ollama embedding request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            detail = _ollama_error_detail(exc.response, self.model_name)
            raise EmbeddingProviderError(detail) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(
                f"Could not connect to Ollama at {self.base_url}: {exc}."
            ) from exc
        except ValueError as exc:
            raise EmbeddingProviderError(
                "Ollama returned malformed JSON for the embedding request."
            ) from exc
        if not isinstance(payload, dict):
            raise EmbeddingProviderError("Ollama returned a malformed response.")
        return payload

    def _discover_dimension(self) -> int:
        payload = self._request_json(
            "post", "/api/show", json={"model": self.model_name}
        )
        model_info = payload.get("model_info")
        detected = None
        if isinstance(model_info, dict):
            for key, value in model_info.items():
                if str(key).endswith(".embedding_length"):
                    try:
                        detected = int(value)
                    except (TypeError, ValueError) as exc:
                        raise EmbeddingProviderError(
                            "Ollama returned invalid embedding dimension metadata."
                        ) from exc
                    break

        if detected is None:
            if self.expected_dimension is None:
                raise EmbeddingProviderError(
                    "Ollama did not report this model's embedding dimension. "
                    "Set OLLAMA_EMBEDDING_DIMENSION and verify it against an embedding response."
                )
            detected = self.expected_dimension
        if self.expected_dimension is not None and detected != self.expected_dimension:
            raise EmbeddingProviderError(
                f"Ollama model {self.model_name!r} reports {detected} dimensions, "
                f"but OLLAMA_EMBEDDING_DIMENSION is {self.expected_dimension}."
            )
        if detected < 1:
            raise EmbeddingProviderError("Ollama reported an invalid embedding dimension.")
        return detected

    def embed(self, text: str) -> list[float]:
        expected_dimension = self.dimension
        payload = self._request_json(
            "post",
            "/api/embed",
            json={"model": self.model_name, "input": text},
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise EmbeddingProviderError("Ollama returned no embedding vector.")
        vector = _validated_vector(embeddings[0], expected_dimension)
        return vector

    def check_available(self) -> dict[str, Any]:
        try:
            payload = self._request_json("get", "/api/tags", timeout=3)
        except EmbeddingError as exc:
            return {
                "available": False,
                "model_available": False,
                "error": str(exc),
            }
        models = payload.get("models")
        if not isinstance(models, list):
            return {
                "available": False,
                "model_available": False,
                "error": "Ollama returned a malformed model list.",
            }
        installed = {
            model.get("name")
            for model in models
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        }
        model_available = self.model_name in installed or (
            self.model_name + ":latest" in installed
        )
        return {
            "available": True,
            "model_available": model_available,
            "error": None
            if model_available
            else f"Model {self.model_name!r} is not installed; run `ollama pull {self.model_name}`.",
        }


class UnconfiguredEmbeddingProvider:
    provider_name = "openai"

    def __init__(self, model: str) -> None:
        self.model_name = model

    @property
    def dimension(self) -> int:
        return OPENAI_EMBEDDING_DIMENSION

    def embed(self, text: str) -> list[float]:
        raise EmbeddingNotConfiguredError(
            "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai."
        )

    def check_available(self) -> dict[str, Any]:
        return {
            "available": False,
            "model_available": False,
            "error": "OPENAI_API_KEY is not configured.",
        }

    def check_available(self) -> dict[str, Any]:
        return {
            "available": False,
            "model_available": False,
            "error": "OPENAI_API_KEY is not configured.",
        }


def get_embedding_provider() -> EmbeddingProvider:
    if EMBEDDING_PROVIDER == "ollama":
        try:
            expected_dimension = int(OLLAMA_EMBEDDING_DIMENSION)
        except ValueError as exc:
            raise ValueError("OLLAMA_EMBEDDING_DIMENSION must be an integer.") from exc
        return OllamaEmbeddingProvider(
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_EMBEDDING_MODEL,
            expected_dimension=expected_dimension,
        )
    if EMBEDDING_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return UnconfiguredEmbeddingProvider(OPENAI_EMBEDDING_MODEL)
        return OpenAIEmbeddingProvider(
            api_key=OPENAI_API_KEY,
            model=OPENAI_EMBEDDING_MODEL,
            timeout_seconds=OPENAI_TIMEOUT_SECONDS,
        )
    raise ValueError(
        "EMBEDDING_PROVIDER must be one of: ollama, openai."
    )


create_embedding_provider = get_embedding_provider
embedding_provider: EmbeddingProvider = get_embedding_provider()


def _ollama_error_detail(response: httpx.Response, model: str) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    if response.status_code == 404 or (
        isinstance(error, str) and "not found" in error.lower()
    ):
        return f"Ollama model {model!r} is unavailable; run `ollama pull {model}`."
    if isinstance(error, str) and error:
        return f"Ollama embedding request failed: {error}"
    return f"Ollama embedding request failed with HTTP {response.status_code}."
