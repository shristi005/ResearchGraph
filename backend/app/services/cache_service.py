"""Caches generated AI text so the same inputs never trigger a second LLM call."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import GEMINI_MODEL, GROQ_MODEL
from app.models.ai import AICache


def make_key(kind: str, *parts) -> str:
    raw = json.dumps([kind, GROQ_MODEL, GEMINI_MODEL, *parts], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def get(db: Session, key: str) -> dict | None:
    row = db.scalar(select(AICache).where(AICache.key == key))
    return json.loads(row.payload) if row else None


def put(db: Session, key: str, kind: str, payload: dict) -> None:
    row = db.scalar(select(AICache).where(AICache.key == key))
    if row:
        row.payload = json.dumps(payload)
    else:
        db.add(AICache(key=key, kind=kind, payload=json.dumps(payload)))
    db.commit()
