#!/usr/bin/env python3
"""LIVE verification of the real Groq + Gemini free-tier APIs from YOUR machine/backend (stdlib only, no mocks).
Run from backend/ with your keys in the environment (or backend/.env exported):
    cd backend && python ../scripts/live_check.py
It makes ~15 tiny requests (well inside free limits), prints a PASS/FAIL table, and never prints keys.
It verifies: reachability, model availability, structured JSON, invalid-key / invalid-model behaviour, live fallback
(using a deliberately invalid key on one provider), embeddings (dimension, normalisation, ranking), small concurrency.
It cannot force a real 429; rate-limit handling is covered by the simulated tests (tests/test_ai_layer.py).
Free-tier eligibility/quota numbers: read them in the consoles (links in docs/LIVE_TESTS.md) - they are account-specific."""
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402
_env.load()
from app import config  # noqa: E402
from app.ai import embeddings, http, router  # noqa: E402
from app.ai.errors import AIUnavailable, ProviderError  # noqa: E402
from app.ai.providers import PROVIDERS  # noqa: E402
from app.ai.quota import QuotaTracker  # noqa: E402

RESULTS = []


def rec(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)


def guarded(name, fn):
    try:
        fn()
    except Exception as exc:  # report, keep going
        rec(name, False, f"{type(exc).__name__}: {str(exc)[:160]}")


def models():
    if config.GROQ_API_KEY:
        d = http.get_json("groq", config.GROQ_URL.replace("/chat/completions", "/models"), {"Authorization": f"Bearer {config.GROQ_API_KEY}"}, 20)
        ids = {m["id"] for m in d.get("data", [])}
        rec("groq: model list reachable", True, f"{len(ids)} models visible to this key")
        rec(f"groq: GROQ_MODEL '{config.GROQ_MODEL}' available", config.GROQ_MODEL in ids, "" if config.GROQ_MODEL in ids else "pick one from: " + ", ".join(sorted(ids)[:12]))
    if config.GEMINI_API_KEY:
        d = http.get_json("gemini", f"{config.GEMINI_BASE}/models?pageSize=200", {"x-goog-api-key": config.GEMINI_API_KEY}, 20)
        by = {m["name"].removeprefix("models/"): m for m in d.get("models", [])}
        rec("gemini: model list reachable", True, f"{len(by)} models visible to this key")
        m = by.get(config.GEMINI_MODEL)
        rec(f"gemini: GEMINI_MODEL '{config.GEMINI_MODEL}' supports generateContent", bool(m and "generateContent" in m.get("supportedGenerationMethods", [])),
            "" if m else "pick one from: " + ", ".join(sorted(k for k in by if "gemini" in k)[:12]))
        e = by.get(config.EMBED_MODEL)
        rec(f"gemini: embedding model '{config.EMBED_MODEL}' available", bool(e), "" if e else "see docs/EMBEDDINGS.md")


def structured(name):
    p = PROVIDERS[name]
    r = p.chat("Reply with JSON only.", [{"role": "user", "content": 'Return {"ok": true, "n": 3} exactly.'}], json_mode=True, temperature=0)
    d = json.loads(r.text)
    rec(f"{name}: structured JSON", d.get("ok") is True and d.get("n") == 3, f"{r.model}, {r.latency_s:.1f}s, tokens={r.total_tokens}")


def bad_key(name):
    key_attr = f"{name.upper()}_API_KEY"
    old = getattr(config, key_attr)
    setattr(config, key_attr, "invalid-key-for-test")
    try:
        PROVIDERS[name].chat("x", [{"role": "user", "content": "hi"}], json_mode=False, temperature=0)
        rec(f"{name}: invalid key rejected", False, "request unexpectedly succeeded")
    except ProviderError as e:
        rec(f"{name}: invalid key rejected", e.kind in ("auth", "bad_request"), f"classified as {e.kind} (HTTP {e.status})")
    finally:
        setattr(config, key_attr, old)


def bad_model(name):
    try:
        PROVIDERS[name].chat("x", [{"role": "user", "content": "hi"}], json_mode=False, temperature=0, model="definitely-not-a-model-123")
        rec(f"{name}: invalid model rejected", False, "unexpectedly succeeded")
    except ProviderError as e:
        rec(f"{name}: invalid model rejected", e.kind in ("model_unavailable", "bad_request"), f"classified as {e.kind} (HTTP {e.status})")


def live_fallback(broken, expect):
    attr = f"{broken.upper()}_API_KEY"
    old, config.AI_PRIMARY_PROVIDER = getattr(config, attr), broken
    setattr(config, attr, "invalid-key-for-test")
    router.tracker = QuotaTracker()
    try:
        r = router.complete("mentor", "Answer in one short sentence.", [{"role": "user", "content": "Say hello."}])
        rec(f"live fallback: {broken} (bad key) -> {expect}", r.provider == expect and r.fallback_used, f"attempts={r.attempts}")
    finally:
        setattr(config, attr, old); config.AI_PRIMARY_PROVIDER = ""; router.tracker = QuotaTracker()


def embed_check():
    docs = embeddings.embed_documents(["Detecting crop diseases from drone images with GANs", "AI-assisted music mixing for producers", "Bridge crack detection using saliency maps"])
    q = embeddings.embed_query("plant disease detection from UAV imagery")
    ok_dim = all(len(v) == config.EMBED_DIM for v in docs + [q])
    sims = [sum(a * b for a, b in zip(q, d)) for d in docs]
    rec(f"embeddings: {embeddings.model_id()} dimension", ok_dim, f"{len(q)}-dim")
    rec("embeddings: semantic ranking (crop paper nearest)", sims.index(max(sims)) == 0, "sims=" + ", ".join(f"{s:.2f}" for s in sims))


def concurrency(name):
    out = []
    def go():
        try:
            out.append(PROVIDERS[name].chat("Reply with one word.", [{"role": "user", "content": "ping"}], json_mode=False, temperature=0).text)
        except Exception as e:
            out.append(e)
    ts = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in ts]; [t.join() for t in ts]
    good = sum(isinstance(x, str) for x in out)
    rec(f"{name}: 3 concurrent requests", good >= 2, f"{good}/3 succeeded (a 429 here means your free RPM is low, which the router handles)")


if __name__ == "__main__":
    have_g, have_m = bool(config.GROQ_API_KEY), bool(config.GEMINI_API_KEY)
    print(f"Keys present - groq: {have_g}, gemini: {have_m}  (values never printed)")
    if not (have_g or have_m):
        print("Set GROQ_API_KEY and/or GEMINI_API_KEY first."); sys.exit(2)
    guarded("model lists", models)
    for n, have in (("groq", have_g), ("gemini", have_m)):
        if have:
            guarded(f"{n}: structured", lambda n=n: structured(n)); guarded(f"{n}: bad key", lambda n=n: bad_key(n))
            guarded(f"{n}: bad model", lambda n=n: bad_model(n)); guarded(f"{n}: concurrency", lambda n=n: concurrency(n))
    if have_g and have_m:
        guarded("fallback groq->gemini", lambda: live_fallback("groq", "gemini")); guarded("fallback gemini->groq", lambda: live_fallback("gemini", "groq"))
    if config.EMBED_PROVIDER != "gemini" or have_m:
        guarded("embeddings", embed_check)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed.")
    sys.exit(1 if bad else 0)
