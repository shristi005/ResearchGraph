# AI routing, fallback and free-tier protection
All generation goes through `backend/app/ai/router.py`; React never calls a provider; keys exist only in backend env vars.
Providers: `groq` (OpenAI-compatible chat endpoint) and `gemini` (generateContent). No other provider, no paid path, no local model.

| Feature (router name) | Used by | Preferred (initial, pre-benchmark) |
|---|---|---|
| extraction | paper analysis JSON | gemini |
| opportunities | opportunity wording, feasibility | gemini |
| explain | paper explanation | groq |
| graph | edge explanations | groq |
| synthesis | graph overview | groq |
| mentor | Research Mentor | groq |
Override: `AI_PRIMARY_PROVIDER=groq|gemini` (all features), `GROQ_MODEL_<FEATURE>` / `GEMINI_MODEL_<FEATURE>` (model per feature). Replace the table after `benchmark_providers.py`.

## Fallback rules (tested in tests/test_ai_layer.py, simulated)
| Event | Behaviour |
|---|---|
| HTTP 429 | no in-place retry; provider cools down (Retry-After or 60 s); other provider tried |
| 5xx / timeout / connection | up to `AI_MAX_RETRIES` same-provider retries with backoff, then other provider |
| 401/403 | other provider; failing provider disabled 10 min |
| 404 / unknown model | other provider |
| 400/422 | **stop**, never forwarded (would fail twice and waste quota) |
| 200 but not a JSON object (JSON tasks) | other provider once; then "could not be used" |
| both fail / skipped | clear "temporarily unavailable" error; nothing is fabricated |
| fallback disabled or other key missing | no second attempt; an unconfigured provider is never contacted |
The fallback request is byte-identical (same system prompt, messages, JSON requirement). Retrieval, paper filters, user scoping and citation rules are applied by the caller *before* the router, so they cannot change with the provider. Callers still validate the schema and the Mentor still strips citation tags that were not retrieved.

## Quota protection
`ai/quota.py` keeps in-process sliding windows (requests/min/day, tokens/min/day) per provider, skips a provider that is over your configured guard, tracks per-feature counts and exposes them at `GET /api/ai/status`. It is a *guard*, not the provider's real counter: set limits from your own consoles. Also: results cached (`ai_cache`), one analysis at a time (`ANALYSIS_LOCK`), concurrency cap `AI_CONCURRENCY`, benchmarks are separate scripts. State resets on restart and is per process.

## Free tier honesty
The code cannot know whether a key's project is billed. Use a Gemini key from a project without billing. Free-tier limits/models change: verify in the consoles; `scripts/live_check.py` confirms the configured model ids are visible to your key. Defaults (`openai/gpt-oss-120b`, `gemini-2.5-flash`) are *candidates*, not verified facts.
