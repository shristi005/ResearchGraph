"""Hosted chat providers (Groq, Gemini). Both are plain HTTPS API calls - no model is downloaded or hosted locally."""
import time

from app.ai import http
from app.ai.errors import MALFORMED, ProviderError
from app.ai.types import AIResult
from app import config


class Provider:
    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def default_model(self) -> str:
        raise NotImplementedError

    def chat(self, system: str, messages: list[dict], *, json_mode: bool, temperature: float,
             model: str | None = None, max_tokens: int | None = None) -> AIResult:
        raise NotImplementedError


class GroqProvider(Provider):
    name = "groq"

    def configured(self) -> bool:
        return bool(config.GROQ_API_KEY)

    def default_model(self) -> str:
        return config.GROQ_MODEL

    def chat(self, system, messages, *, json_mode, temperature, model=None, max_tokens=None) -> AIResult:
        model = model or self.default_model()
        payload = {"model": model, "temperature": temperature,
                   "messages": [{"role": "system", "content": system}, *messages]}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        data = http.post_json(self.name, config.GROQ_URL, {"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                              payload, config.AI_TIMEOUT)
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                self.name, MALFORMED, "groq returned an unexpected response shape.") from exc
        u = data.get("usage") or {}
        return AIResult(text, self.name, model, time.monotonic() - t0,
                        u.get("prompt_tokens"), u.get("completion_tokens"))


class GeminiProvider(Provider):
    name = "gemini"

    def configured(self) -> bool:
        return bool(config.GEMINI_API_KEY)

    def default_model(self) -> str:
        return config.GEMINI_MODEL

    def chat(self, system, messages, *, json_mode, temperature, model=None, max_tokens=None) -> AIResult:
        model = model or self.default_model()
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages]
        gen = {"temperature": temperature}
        if max_tokens:
            gen["maxOutputTokens"] = max_tokens
        if json_mode:
            gen["responseMimeType"] = "application/json"
        payload = {"systemInstruction": {
            "parts": [{"text": system}]}, "contents": contents, "generationConfig": gen}
        t0 = time.monotonic()
        data = http.post_json(self.name, f"{config.GEMINI_BASE}/models/{model}:generateContent",
                              {"x-goog-api-key": config.GEMINI_API_KEY}, payload, config.AI_TIMEOUT)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            # Safety blocks / empty candidates land here.
            raise ProviderError(self.name, MALFORMED,
                                "gemini returned no usable answer.") from exc
        u = data.get("usageMetadata") or {}
        return AIResult(text, self.name, model, time.monotonic() - t0,
                        u.get("promptTokenCount"), u.get("candidatesTokenCount"))


class OllamaProvider(Provider):
    """Ollama on your own machine. Reached through the token gate + Cloudflare tunnel when the backend is in the cloud."""
    name = "ollama"

    def configured(self) -> bool:
        return bool(config.OLLAMA_URL)

    def default_model(self) -> str:
        return config.OLLAMA_MODEL

    def chat(self, system, messages, *, json_mode, temperature, model=None, max_tokens=None) -> AIResult:
        model = model or self.default_model()
        opts = {"temperature": temperature, "num_ctx": config.OLLAMA_NUM_CTX}
        if max_tokens:
            opts["num_predict"] = max_tokens
        payload = {"model": model, "stream": True, "options": opts,
                   "messages": [{"role": "system", "content": system}, *messages]}
        if json_mode:
            payload["format"] = "json"
        headers = {
            "Authorization": f"Bearer {config.OLLAMA_GATE_TOKEN}"} if config.OLLAMA_GATE_TOKEN else {}
        t0 = time.monotonic()
        lines = http.post_ndjson(self.name, f"{config.OLLAMA_URL}/api/chat", headers, payload,
                                 config.OLLAMA_TIMEOUT, config.OLLAMA_TOTAL_TIMEOUT)
        text, last = [], {}
        for ln in lines:
            if ln.get("error"):
                # e.g. "model 'x' not found" arrives as an error line on some versions
                kind = "model_unavailable" if "not found" in str(
                    ln["error"]).lower() else MALFORMED
                raise ProviderError(
                    self.name, kind, "ollama reported an error.")
            text.append((ln.get("message") or {}).get("content", ""))
            if ln.get("done"):
                last = ln
        if not last:
            raise ProviderError(self.name, MALFORMED,
                                "ollama stream ended early.")
        return AIResult("".join(text).strip(), self.name, model, time.monotonic() - t0,
                        last.get("prompt_eval_count"), last.get("eval_count"))


PROVIDERS: dict[str, Provider] = {"groq": GroqProvider(
), "gemini": GeminiProvider(), "ollama": OllamaProvider()}
