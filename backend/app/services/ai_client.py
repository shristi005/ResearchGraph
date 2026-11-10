"""Thin facade used by the feature services. Replaces the old Ollama client with the Groq/Gemini router.
The function names/shapes are kept so the services stay almost unchanged."""
import json

from app.ai import embeddings, router
from app.ai.errors import AIError, AIUnavailable  # noqa: F401  (re-exported for callers)

# llm_service task name -> routing feature
TASK_FEATURE = {
    "extraction": "extraction", "gap_details": "opportunities", "feasibility": "opportunities",
    "node_explain": "explain", "edge_explain": "graph", "graph_overview": "synthesis", "mentor": "mentor",
}


def feature_for(task: str) -> str:
    return TASK_FEATURE.get(task, "default")


def chat_json(prompt: str, system: str, feature: str = "extraction") -> dict:
    res = router.complete(feature, system, [{"role": "user", "content": prompt}], json_mode=True, temperature=0.0)
    try:
        data = json.loads(res.text)
    except json.JSONDecodeError as exc:
        raise ValueError("The AI did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("The AI JSON was not an object.")
    return data


def chat_text(messages: list[dict], system: str, feature: str = "mentor") -> str:
    return router.complete(feature, system, messages, json_mode=False, temperature=0.2).text


def embed_documents(texts: list[str]) -> list[list[float]]:
    return embeddings.embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return embeddings.embed_query(text)


def status() -> dict:
    s = router.status()
    llm_ready = any(p["configured"] for p in s["providers"].values())
    emb_ready, emb_msg = embeddings.ready()
    msgs = []
    if not llm_ready:
        msgs.append("No AI provider configured: set GROQ_API_KEY and/or GEMINI_API_KEY on the backend.")
    if not emb_ready:
        msgs.append(emb_msg)
    return {"llm_ready": llm_ready, "embedding_ready": emb_ready, "providers": s["providers"],
            "fallback_enabled": s["fallback_enabled"], "routing": s["routing"], "quota": s["quota"],
            "embed_model": embeddings.model_id(),
            "message": " ".join(msgs) or "AI providers are configured."}
