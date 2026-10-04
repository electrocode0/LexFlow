import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "******localhost:5432/lexflow"
)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").strip().lower()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b").strip()
OLLAMA_EMBEDDING_MODEL = os.getenv(
    "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
).strip()
OLLAMA_EMBEDDING_DIMENSION = os.getenv("OLLAMA_EMBEDDING_DIMENSION", "768").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
OPENAI_LLM_MODEL = os.getenv(
    "OPENAI_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")
).strip()
OPENAI_MODEL = OPENAI_LLM_MODEL
OPENAI_EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
).strip()
OPENAI_EMBEDDING_DIMENSION = 768

AI_PROVIDER_TIMEOUT_SECONDS = float(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "60"))
OPENAI_TIMEOUT_SECONDS = float(
    os.getenv("OPENAI_TIMEOUT_SECONDS", str(AI_PROVIDER_TIMEOUT_SECONDS))
)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
