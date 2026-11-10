"""In-process free-tier guard: sliding-window request/token counters + cooldown after HTTP 429.

This protects the free quota; it does NOT know your real remaining quota (only the provider does). Limits are
configurable (see config.py) and should be set from your own console values. State resets on restart and is
per-process - fine for a single free Render instance."""
import threading
import time
from collections import defaultdict, deque

from app import config


class QuotaTracker:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque] = defaultdict(
            deque)     # provider -> (ts, tokens)
        self._cooldown_until: dict[str, float] = {}
        self._disabled_until: dict[str, float] = {}
        self.totals: dict[str, dict] = defaultdict(
            lambda: {"requests": 0, "tokens": 0, "errors": 0, "fallbacks_in": 0})
        self.per_feature: dict[str, int] = defaultdict(int)

    def _prune(self, provider: str, now: float) -> None:
        q = self._events[provider]
        while q and now - q[0][0] > 86400:
            q.popleft()

    def _window(self, provider: str, seconds: int, now: float) -> tuple[int, int]:
        reqs = toks = 0
        for ts, t in self._events[provider]:
            if now - ts <= seconds:
                reqs += 1
                toks += t
        return reqs, toks

    def available(self, provider: str, est_tokens: int = 0) -> tuple[bool, str]:
        lim = config.PROVIDER_LIMITS.get(provider, {})
        with self._lock:
            now = self._clock()
            if self._disabled_until.get(provider, 0) > now:
                return False, "disabled (authentication failed recently)"
            if self._cooldown_until.get(provider, 0) > now:
                return False, "cooling down after a rate-limit response"
            self._prune(provider, now)
            rm, tm = self._window(provider, 60, now)
            rd, td = self._window(provider, 86400, now)
            if lim.get("rpm") and rm >= lim["rpm"]:
                return False, "local requests/minute guard reached"
            if lim.get("rpd") and rd >= lim["rpd"]:
                return False, "local requests/day guard reached"
            if lim.get("tpm") and tm + est_tokens > lim["tpm"]:
                return False, "local tokens/minute guard reached"
            if lim.get("tpd") and td + est_tokens > lim["tpd"]:
                return False, "local tokens/day guard reached"
        return True, "ok"

    def record(self, provider: str, tokens: int | None, feature: str, *, fallback: bool = False) -> None:
        with self._lock:
            self._events[provider].append((self._clock(), int(tokens or 0)))
            t = self.totals[provider]
            t["requests"] += 1
            t["tokens"] += int(tokens or 0)
            if fallback:
                t["fallbacks_in"] += 1
            self.per_feature[feature] += 1

    def record_error(self, provider: str, kind: str, retry_after: float | None = None) -> None:
        with self._lock:
            now = self._clock()
            self.totals[provider]["errors"] += 1
            if kind == "rate_limit":
                self._cooldown_until[provider] = now + \
                    (retry_after if retry_after else config.RATE_LIMIT_COOLDOWN_S)
            elif kind == "auth":
                self._disabled_until[provider] = now + 600

    def snapshot(self) -> dict:
        with self._lock:
            now = self._clock()
            out = {}
            for p in ("groq", "gemini", "ollama"):
                rm, tm = self._window(p, 60, now)
                rd, td = self._window(p, 86400, now)
                out[p] = {**self.totals[p], "last_minute_requests": rm, "last_minute_tokens": tm,
                          "last_day_requests": rd, "last_day_tokens": td,
                          "cooling_down": self._cooldown_until.get(p, 0) > now,
                          "disabled": self._disabled_until.get(p, 0) > now}
            return {"providers": out, "per_feature_requests": dict(self.per_feature)}


tracker = QuotaTracker()
