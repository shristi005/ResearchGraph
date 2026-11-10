"""Tiny .env loader for the helper scripts (uvicorn loads it itself via --env-file). Stdlib only."""
import os
from pathlib import Path


def load(path: Path | None = None) -> None:
    p = path or Path(__file__).resolve().parent.parent / "backend" / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #")[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)
