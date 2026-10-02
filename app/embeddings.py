from typing import Any, Protocol

from openai import APITimeoutError, OpenAI, OpenAIError

from app.config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_DIMENSION,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, text: str) -> list[float]:
        ...


class EmbeddingError(Exception):
    pass


class EmbeddingNotConfiguredError(EmbeddingError):
    pass


class EmbeddingTimeoutError(EmbeddingError):
    pass


class EmbeddingProviderError(EmbeddingError):
    pass


class OpenAIEmbeddingProvider:
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
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout_seconds)

    def embed(self, text: str) -> list[float]:
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimension,
            )
        except APITimeoutError as exc:
            raise EmbeddingTimeoutError("The embedding request timed out.") from exc
        except OpenAIError as exc:
            raise EmbeddingProviderError("The embedding request failed.") from exc

        if not response.data:
            raise EmbeddingProviderError("The embedding provider returned no vector.")
        vector = response.data[0].embedding
        if len(vector) != self.dimension:
            raise EmbeddingProviderError(
                f"Expected {self.dimension}-dimensional embeddings, got {len(vector)}."
            )
        return vector


class UnconfiguredEmbeddingProvider:
    dimension = OPENAI_EMBEDDING_DIMENSION

    def embed(self, text: str) -> list[float]:
        raise EmbeddingNotConfiguredError(
            "The semantic embedding provider is not configured."
        )


def create_embedding_provider() -> EmbeddingProvider:
    if not OPENAI_API_KEY:
        return UnconfiguredEmbeddingProvider()
    return OpenAIEmbeddingProvider(
        api_key=OPENAI_API_KEY,
        model=OPENAI_EMBEDDING_MODEL,
        timeout_seconds=OPENAI_TIMEOUT_SECONDS,
    )


embedding_provider: EmbeddingProvider = create_embedding_provider()