"""Embedding generation - deliberately separate from chat generation and from vector storage.

Providers (EMBED_PROVIDER), all 768-dimensional so the pgvector column never changes:
  gemini : Gemini Developer API embedContent (free-tier eligible; verify current limits). Truncated to 768 + L2-normalised.
  local  : fastembed (ONNX) running nomic-ai/nomic-embed-text-v1.5 inside the backend process. Same family as the old
           `nomic-embed-text`, no Ollama, no external call. Needs `pip install fastembed` and ~0.5-1 GB RAM (too big for
           Render's free 512 MB instance; fine on a laptop or a bigger host).
  hash   : deterministic bag-of-words hashing. TESTS / OFFLINE DEMO ONLY - not semantic enough for real use.
Vectors from different models are NEVER comparable: every stored vector records its model id and retrieval filters on it.
"""
import hashlib
import math
import re
import threading

from app import config
from app.ai import http
from app.ai.errors import AIUnavailable, ProviderError
from app.ai.quota import tracker

_local_model = None
_local_lock = threading.Lock()


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def model_id() -> str:
    return f"{config.EMBED_PROVIDER}:{config.EMBED_MODEL}:{config.EMBED_DIM}"


def _hash_embed(text: str) -> list[float]:
    v = [0.0] * config.EMBED_DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % config.EMBED_DIM] += 1.0
    return _normalize(v)


def _gemini_embed(texts: list[str], task: str) -> list[list[float]]:
    if not config.GEMINI_API_KEY:
        raise AIUnavailable(
            "Embeddings need GEMINI_API_KEY (or set EMBED_PROVIDER=local).")
    ok, why = tracker.available("gemini")
    if not ok:
        raise AIUnavailable(
            "Embedding quota is temporarily used up. Please try again in a few minutes.")
    out: list[list[float]] = []
    for i in range(0, len(texts), min(config.EMBED_BATCH, 100)):
        batch = texts[i:i + min(config.EMBED_BATCH, 100)]
        payload = {"requests": [{"model": f"models/{config.EMBED_MODEL}", "content": {"parts": [{"text": t}]},
                                 "taskType": task, "outputDimensionality": config.EMBED_DIM} for t in batch]}
        try:
            data = http.post_json("gemini", f"{config.GEMINI_BASE}/models/{config.EMBED_MODEL}:batchEmbedContents",
                                  {"x-goog-api-key": config.GEMINI_API_KEY}, payload, config.AI_TIMEOUT)
        except ProviderError as exc:
            tracker.record_error("gemini", exc.kind, exc.retry_after)
            raise AIUnavailable(
                "The embedding service is temporarily unavailable. Please try again shortly.") from exc
        tracker.record("gemini", sum(len(t) for t in batch) // 4, "embedding")
        vecs = [e.get("values") for e in data.get("embeddings", [])]
        if len(vecs) != len(batch) or any(not v or len(v) != config.EMBED_DIM for v in vecs):
            raise AIUnavailable(
                "The embedding service returned unexpected vectors.")
        out += [_normalize(v) for v in vecs]
    return out


def _ollama_embed(texts: list[str], prefix: str) -> list[list[float]]:
    if not config.OLLAMA_URL:
        raise AIUnavailable(
            "Embeddings need OLLAMA_URL (or another EMBED_PROVIDER).")
    headers = {
        "Authorization": f"Bearer {config.OLLAMA_GATE_TOKEN}"} if config.OLLAMA_GATE_TOKEN else {}
    out: list[list[float]] = []
    for i in range(0, len(texts), 16):
        batch = [prefix + t for t in texts[i:i + 16]]
        try:
            data = http.post_json("ollama", f"{config.OLLAMA_URL}/api/embed", headers,
                                  {"model": config.EMBED_MODEL, "input": batch}, config.OLLAMA_TIMEOUT)
        except ProviderError as exc:
            if exc.kind == "model_unavailable":
                raise AIUnavailable(
                    f"Embedding model '{config.EMBED_MODEL}' is not installed. Run: ollama pull {config.EMBED_MODEL}") from exc
            raise AIUnavailable(
                "The embedding service (Ollama) is unreachable. Is Ollama running and the tunnel up?") from exc
        vecs = data.get("embeddings") or []
        if len(vecs) != len(batch) or any(len(v) != config.EMBED_DIM for v in vecs):
            raise AIUnavailable(
                f"Ollama returned unexpected embeddings (expected {config.EMBED_DIM} dimensions).")
        out += [_normalize([float(x) for x in v]) for v in vecs]
    return out


def _local_embed(texts: list[str], prefix: str) -> list[list[float]]:
    global _local_model
    with _local_lock:
        if _local_model is None:
            try:
                from fastembed import TextEmbedding  # optional dependency
            except ImportError as exc:
                raise AIUnavailable(
                    "EMBED_PROVIDER=local needs `pip install fastembed`.") from exc
            _local_model = TextEmbedding(model_name=config.EMBED_MODEL)
        return [_normalize([float(x) for x in v]) for v in _local_model.embed([prefix + t for t in texts])]


def _embed(texts: list[str], kind: str) -> list[list[float]]:
    if not texts:
        return []
    p = config.EMBED_PROVIDER
    if p == "gemini":
        return _gemini_embed(texts, "RETRIEVAL_DOCUMENT" if kind == "document" else "RETRIEVAL_QUERY")
    if p == "ollama":   # nomic-embed-text is trained with these task prefixes
        return _ollama_embed(texts, "search_document: " if kind == "document" else "search_query: ")
    if p == "local":
        return _local_embed(texts, "search_document: " if kind == "document" else "search_query: ")
    if p == "hash":
        return [_hash_embed(t) for t in texts]
    raise AIUnavailable(f"Unknown EMBED_PROVIDER '{p}'.")


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "document")


def embed_query(text: str) -> list[float]:
    return _embed([text], "query")[0]


def ready() -> tuple[bool, str]:
    p = config.EMBED_PROVIDER
    if p == "gemini" and not config.GEMINI_API_KEY:
        return False, "Embeddings need GEMINI_API_KEY (or EMBED_PROVIDER=local)."
    if p == "ollama" and not config.OLLAMA_URL:
        return False, "Embeddings need OLLAMA_URL (Ollama address)."
    if p == "local":
        try:
            import fastembed  # noqa: F401
        except ImportError:
            return False, "EMBED_PROVIDER=local needs `pip install fastembed`."
    if p not in ("ollama", "gemini", "local", "hash"):
        return False, f"Unknown EMBED_PROVIDER '{p}'."
    return True, "ok"
