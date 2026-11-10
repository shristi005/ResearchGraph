"""Centralised feature-based routing with safe fallback between Groq and Gemini (both FREE tiers only).

Rules (see docs/AI_ROUTING.md):
  * one preferred provider per feature; the other is used only on rate-limit / transient / auth / unavailable-model
    / malformed output, and only if it is configured, locally under its guard limits, and fallback is enabled.
  * bad requests (400/422) are never forwarded to the second provider.
  * same-provider retries: transient errors only, at most AI_MAX_RETRIES, with backoff. 429 is never retried in place.
  * the identical system prompt, messages and JSON requirement go to the fallback: grounding, paper filters and
    citation rules live in the prompt/evidence built by the caller and are not altered here.
"""
import json
import logging
import threading
import time

from app import config
from app.ai.errors import (AUTH, BAD_REQUEST, MALFORMED, MODEL_UNAVAILABLE, RATE_LIMIT, TRANSIENT, AIConfigError,
                           AIUnavailable, ProviderError)
from app.ai.providers import PROVIDERS
from app.ai.quota import tracker
from app.ai.types import AIResult

log = logging.getLogger("researchgraph.ai")

# Initial allocation from the project brief; override per deployment with AI_PRIMARY_PROVIDER or after benchmarking.
FEATURE_PROVIDER = {
    "extraction": "gemini",       # structured paper extraction
    "opportunities": "gemini",    # research opportunity wording / feasibility
    "explain": "groq",            # paper explanations
    "graph": "groq",              # graph + edge explanations
    "mentor": "groq",             # research mentor
    "synthesis": "groq",          # multi-paper synthesis
    "default": "groq",
}

_SEM = threading.BoundedSemaphore(max(1, config.AI_CONCURRENCY))
_sleep = time.sleep  # patched in tests


def preferred(feature: str) -> str:
    if config.AI_PRIMARY_PROVIDER in PROVIDERS:
        return config.AI_PRIMARY_PROVIDER
    return FEATURE_PROVIDER.get(feature, FEATURE_PROVIDER["default"])


def _order(feature: str) -> list[str]:
    first = preferred(feature)
    rest = [n for n in ("gemini", "groq", "ollama") if n != first]
    names = [first] + (rest if config.AI_FALLBACK_ENABLED else [])
    return [n for n in names if PROVIDERS[n].configured()]


def _estimate_tokens(system: str, messages: list[dict]) -> int:
    return (len(system) + sum(len(m["content"]) for m in messages)) // 4 + 800


def _valid_json_object(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except (ValueError, TypeError):
        return False


def complete(feature: str, system: str, messages: list[dict], *, json_mode: bool = False,
             temperature: float = 0.0, max_tokens: int | None = None) -> AIResult:
    order = _order(feature)
    if not order:
        raise AIConfigError(
            "No AI provider is configured. Set GROQ_API_KEY and/or GEMINI_API_KEY on the backend.")
    est = _estimate_tokens(system, messages)
    attempts: list[str] = []
    last: ProviderError | None = None

    for idx, name in enumerate(order):
        prov = PROVIDERS[name]
        ok, why = tracker.available(name, est)
        if not ok:
            attempts.append(f"{name}:skipped({why})")
            continue
        tries = 0
        while True:
            try:
                with _SEM:
                    res = prov.chat(system, messages, json_mode=json_mode, temperature=temperature,
                                    model=config.feature_model(name, feature), max_tokens=max_tokens)
                if json_mode and not _valid_json_object(res.text):
                    raise ProviderError(
                        name, MALFORMED, f"{name} did not return a JSON object.")
            except ProviderError as exc:
                last = exc
                tracker.record_error(name, exc.kind, exc.retry_after)
                attempts.append(f"{name}:{exc.kind}")
                log.warning("ai feature=%s provider=%s error=%s status=%s",
                            feature, name, exc.kind, exc.status)
                if exc.kind == BAD_REQUEST:
                    # Our request is invalid; the other provider would reject it too. Stop - do not burn quota.
                    raise AIUnavailable(
                        "The AI request was rejected as invalid. Please try again or report this.") from exc
                if exc.kind == TRANSIENT and tries < config.AI_MAX_RETRIES:
                    tries += 1
                    _sleep(min(2 ** tries, 8))
                    continue
                break  # rate_limit / auth / model_unavailable / malformed / exhausted transient -> next provider
            else:
                tracker.record(name, res.total_tokens or est,
                               feature, fallback=idx > 0)
                attempts.append(f"{name}:ok")
                res.attempts = attempts
                res.fallback_used = any(not a.startswith(name)
                                        for a in attempts[:-1])
                log.info("ai feature=%s provider=%s model=%s latency=%.2fs tokens=%s fallback=%s", feature, name,
                         res.model, res.latency_s, res.total_tokens, res.fallback_used)
                return res

    # Nothing worked. Never fabricate an answer.
    if last is not None and last.kind == MALFORMED:
        raise ValueError(
            "The AI returned an answer that could not be used. Please try again.")
    if last is not None and last.kind == AUTH and len(order) == 1:
        raise AIConfigError(
            "The AI provider rejected its API key. Check the backend configuration.")
    raise AIUnavailable("The AI service is temporarily unavailable (a free quota is used up, or the Ollama computer/tunnel "
                        "is offline). Please try again in a few minutes.")


def status() -> dict:
    return {"providers": {n: {"configured": p.configured(), "model": p.default_model()} for n, p in PROVIDERS.items()},
            "fallback_enabled": config.AI_FALLBACK_ENABLED,
            "routing": {f: preferred(f) for f in FEATURE_PROVIDER if f != "default"},
            "quota": tracker.snapshot()}
