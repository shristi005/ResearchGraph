"""Persistent PDF storage. Production: private Supabase Storage bucket, object key "<user_id>/<sha256>.pdf".
Dev/offline: local folder. Render's disk is ephemeral, so nothing permanent is ever kept there in production.
The service-role key is used ONLY here, server-side, after the caller has already verified ownership."""
from pathlib import Path
from urllib.parse import quote

from app import config
from app.config import UPLOAD_DIR


class StorageError(Exception):
    """Message is safe to show."""


def key_for(user_id: str, digest: str) -> str:
    return f"{user_id}/{digest}.pdf"


def _headers(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
         "apikey": config.SUPABASE_SERVICE_ROLE_KEY}
    return {**h, **(extra or {})}


def _url(key: str) -> str:
    return f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{quote(key)}"


def save(user_id: str, digest: str, data: bytes) -> str:
    key = key_for(user_id, digest)
    if config.STORAGE_BACKEND != "supabase":
        path = UPLOAD_DIR / user_id / f"{digest}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
    import httpx
    try:
        r = httpx.post(_url(key), headers=_headers({"Content-Type": "application/pdf", "x-upsert": "true"}),
                       content=data, timeout=60)
    except httpx.HTTPError as exc:
        raise StorageError("Could not reach file storage.") from exc
    if r.status_code >= 300:
        raise StorageError(
            f"File storage rejected the upload (HTTP {r.status_code}): {r.text[:200]}")
    return key


def read(stored_path: str) -> bytes | None:
    if config.STORAGE_BACKEND != "supabase":
        p = Path(stored_path)
        return p.read_bytes() if p.exists() else None
    import httpx
    try:
        r = httpx.get(_url(stored_path), headers=_headers(), timeout=60)
    except httpx.HTTPError as exc:
        raise StorageError("Could not reach file storage.") from exc
    if r.status_code == 404 or r.status_code == 400:
        return None
    if r.status_code >= 300:
        raise StorageError(f"File storage error (HTTP {r.status_code}).")
    return r.content


def delete(stored_path: str) -> None:
    if config.STORAGE_BACKEND != "supabase":
        Path(stored_path).unlink(missing_ok=True)
        return
    import httpx
    try:
        httpx.delete(_url(stored_path), headers=_headers(), timeout=30)
    except httpx.HTTPError:
        pass  # best effort; the DB row is the source of truth and the object is private
