from dataclasses import dataclass, field


@dataclass
class AIResult:
    """Provider-neutral response. The rest of the app never needs to know who produced it."""
    text: str
    provider: str
    model: str
    latency_s: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    fallback_used: bool = False
    attempts: list[str] = field(default_factory=list)  # e.g. ["groq:rate_limit", "gemini:ok"]

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)
