import hashlib
import math
import re
from abc import ABC, abstractmethod

EMBEDDING_DIMENSION = 128
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(ABC):
    dimension = EMBEDDING_DIMENSION

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local baseline; replace with a hosted model later."""

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector


embedding_provider: EmbeddingProvider = HashEmbeddingProvider()