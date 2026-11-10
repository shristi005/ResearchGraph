"""Validated, retried LLM calls shared by every explanation feature."""
import json

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.services import ai_client
from app.services.research_extraction_service import ANALYSIS_LOCK


class LLMModel(BaseModel):
    """Small models return lists where strings are expected and vice versa; coerce instead of failing."""
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data):
        if not isinstance(data, dict):
            return data
        out = dict(data)

        def flat(x):
            if isinstance(x, dict):
                return "; ".join(f"{k}: {v}" for k, v in x.items())
            return str(x)

        for name, f in cls.model_fields.items():
            if name not in out:
                continue
            v, ann = out[name], str(f.annotation)
            if ann.startswith("list"):
                if v is None:
                    out[name] = []
                elif isinstance(v, str):
                    out[name] = [x.strip("-•* ").strip() for x in v.split("\n") if x.strip("-•* ").strip()]
                elif isinstance(v, list):
                    out[name] = [x if isinstance(x, str) else flat(x) for x in v]
            elif "str" in ann and v is not None:
                out[name] = "; ".join(flat(x) for x in v) if isinstance(v, list) else flat(v)
        return out


def call_json(task: str, system: str, prompt: str, model_cls: type[BaseModel], attempts: int = 2):
    """One locked, validated JSON call. Raises AIError (unavailable) or ValueError (bad output)."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            with ANALYSIS_LOCK:
                data = ai_client.chat_json(prompt, f"TASK:{task}\n{system}", ai_client.feature_for(task))
            return model_cls.model_validate(data)
        except (ValueError, ValidationError) as exc:
            last = exc
    raise ValueError(f"The model's answer for “{task}” was not valid after {attempts} attempts ({last}).")


def call_text(task: str, system: str, messages: list[dict]) -> str:
    with ANALYSIS_LOCK:
        return ai_client.chat_text(messages, f"TASK:{task}\n{system}", ai_client.feature_for(task))
