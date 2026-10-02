import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
"DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/lexflow",)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_EMBEDDING_MODEL = os.getenv(
	"OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
).strip()
OPENAI_EMBEDDING_DIMENSION = 1536
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
CORS_ORIGINS = [
	origin.strip()
	for origin in os.getenv(
		"CORS_ORIGINS",
		"http://localhost:5173,http://127.0.0.1:5173",
	).split(",")
	if origin.strip()
]
