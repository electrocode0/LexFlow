import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
"DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/lexflow",)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
