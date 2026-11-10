import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RG_DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"

# --- Database: Supabase Postgres in production, SQLite only for local/offline tests ---
# Use the Supabase *pooler* connection string (Project Settings -> Database -> Connection string), e.g.
# postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL = os.getenv(
    "DATABASE_URL") or f"sqlite:///{DATA_DIR / 'researchgraph.db'}"
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

# --- Supabase (auth + storage). Service-role key is backend-only and used ONLY for Storage. ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
# optional: legacy HS256 projects, offline verification
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "papers")
STORAGE_BACKEND = os.getenv(
    "STORAGE_BACKEND", "supabase" if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else "local")
# AUTH_DISABLED=true  -> single built-in local user. Refused automatically when ENV=production.
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "false").lower(
) == "true" and os.getenv("ENV", "dev") != "production"
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000000"

MAX_UPLOAD_MB = 25
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MIN_TEXT_CHARS = 200  # below this the PDF is probably scanned/image-only


CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

LLM_HEAD_CHARS = 4500           # title/authors/abstract live at the start
LLM_TAIL_CHARS = 3000           # limitations/future work live near the end

# --- Relationship thresholds (all tunable) ---
# min cosine similarity for a semantic_similarity edge
SIM_THRESHOLD = float(os.getenv("RG_SIM_THRESHOLD", 0.70))
# keeps the graph readable
SIM_MAX_EDGES_PER_NODE = int(os.getenv("RG_SIM_MAX_EDGES_PER_NODE", 4))
# min shared topics/keywords for a shared_topic edge
TOPIC_MIN_SHARED = int(os.getenv("RG_TOPIC_MIN_SHARED", 2))
# min shared methodologies/algorithms for a shared_methodology edge
METHOD_MIN_SHARED = int(os.getenv("RG_METHOD_MIN_SHARED", 1))
# min title-match confidence against a reference entry
CITATION_MIN_CONFIDENCE = float(os.getenv("RG_CITATION_MIN_CONFIDENCE", 0.90))
MAX_GAP_HYPOTHESES = 12

# --- Research Mentor (RAG) ---
MENTOR_TOP_K = int(os.getenv("RG_MENTOR_TOP_K", 6))
CHUNK_CHARS = 900

# --- Generative AI: hosted FREE-tier APIs only (Groq + Gemini). No local model, no paid fallback exists in code. ---
# Model IDs change; verify against console.groq.com/docs/models and ai.google.dev/gemini-api/docs/models
# --- Ollama (your own machine, reached from the cloud through a Cloudflare tunnel) ---
# "" = Ollama not used. Local: http://localhost:11434  Cloud: https://xxxx.trycloudflare.com
OLLAMA_URL = os.getenv("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# shared secret checked by scripts/ollama_gate.py (Ollama itself has no login)
OLLAMA_GATE_TOKEN = os.getenv("OLLAMA_GATE_TOKEN", "")
# max silence while waiting for the next piece of output
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", 300))
OLLAMA_TOTAL_TIMEOUT = float(os.getenv("OLLAMA_TOTAL_TIMEOUT", 900))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", 8192))

# overridable for tests only
GROQ_URL = os.getenv(
    "GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
GEMINI_BASE = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# "" = per-feature table in ai/router.py; or groq|gemini|ollama to force
AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "")
AI_FALLBACK_ENABLED = os.getenv(
    "AI_FALLBACK_ENABLED", "true").lower() == "true"
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", 60))
# extra attempts on the SAME provider, transient errors only
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 1))
AI_CONCURRENCY = int(os.getenv("AI_CONCURRENCY", 2))
RATE_LIMIT_COOLDOWN_S = float(os.getenv("AI_RATE_LIMIT_COOLDOWN_S", 60))
# Optional per-model overrides per feature, e.g. GROQ_MODEL_MENTOR=openai/gpt-oss-20b


def feature_model(provider: str, feature: str) -> str | None:
    return os.getenv(f"{provider.upper()}_MODEL_{feature.upper()}") or None


# Local safety guards (0 = off). Set these a little BELOW your real console limits. Defaults are deliberately conservative
# placeholders - they are NOT verified free-tier numbers.
PROVIDER_LIMITS = {
    "groq": {"rpm": int(os.getenv("GROQ_RPM", 25)), "rpd": int(os.getenv("GROQ_RPD", 900)),
             "tpm": int(os.getenv("GROQ_TPM", 6000)), "tpd": int(os.getenv("GROQ_TPD", 150000))},
    "gemini": {"rpm": int(os.getenv("GEMINI_RPM", 8)), "rpd": int(os.getenv("GEMINI_RPD", 200)),
               "tpm": int(os.getenv("GEMINI_TPM", 200000)), "tpd": int(os.getenv("GEMINI_TPD", 0))},
}

# --- Embeddings (separate from generation). All options produce 768-dim vectors so one pgvector column fits all. ---
# ollama | gemini | local | hash (hash = tests only)
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "gemini")
EMBED_MODEL = os.getenv("EMBED_MODEL", {"gemini": "gemini-embedding-001", "local": "nomic-ai/nomic-embed-text-v1.5", "ollama": OLLAMA_EMBED_MODEL}.get(
    os.getenv("EMBED_PROVIDER", "gemini"), "hash-768"))
EMBED_DIM = 768
EMBED_BATCH = int(os.getenv("EMBED_BATCH", 50))
