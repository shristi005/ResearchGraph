"""Supabase access-token verification with no third-party dependency (stdlib only, unit-testable).

Two modes:
  * HS256 (legacy Supabase projects): verified locally with SUPABASE_JWT_SECRET (signature, exp, aud).
  * Anything else (asymmetric signing keys, the default for new projects): the token is validated by Supabase itself
    via GET {SUPABASE_URL}/auth/v1/user, with a short in-memory cache so a page load does not cost many round-trips.
"""
import base64
import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass

from app import config


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None


class AuthError(Exception):
    pass


def _b64d(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def verify_hs256(token: str, secret: str, now: float | None = None) -> User:
    try:
        h, p, s = token.split(".")
        header = json.loads(_b64d(h))
        payload = json.loads(_b64d(p))
        sig = _b64d(s)
    except Exception as exc:
        raise AuthError("Malformed token.") from exc
    if header.get("alg") != "HS256":
        raise AuthError("Unsupported token algorithm.")
    expected = hmac.new(
        secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        raise AuthError("Invalid token signature.")
    if float(payload.get("exp", 0)) < (now if now is not None else time.time()):
        raise AuthError("Session expired. Please sign in again.")
    if payload.get("aud") not in ("authenticated", None):
        raise AuthError("Token is not a user session token.")
    if not payload.get("sub"):
        raise AuthError("Token has no subject.")
    return User(id=payload["sub"], email=payload.get("email"))


def token_alg(token: str) -> str | None:
    try:
        return json.loads(_b64d(token.split(".")[0])).get("alg")
    except Exception:
        return None


_cache: dict[str, tuple[float, User]] = {}
_lock = threading.Lock()
CACHE_TTL = 60.0


def verify_remote(token: str, fetch=None) -> User:
    """fetch(url, headers) -> (status, json). Injected in tests; defaults to httpx."""
    key = hashlib.sha256(token.encode()).hexdigest()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    if not config.SUPABASE_URL:
        raise AuthError("Authentication is not configured on the server.")
    headers = {"Authorization": f"Bearer {token}",
               "apikey": config.SUPABASE_ANON_KEY}
    if fetch is None:
        def fetch(url, headers):
            import httpx
            try:
                r = httpx.get(url, headers=headers, timeout=10)
            except httpx.HTTPError as exc:
                raise AuthError(
                    "Could not reach the authentication service.") from exc
            return r.status_code, (r.json() if r.status_code == 200 else {})
    status, body = fetch(f"{config.SUPABASE_URL}/auth/v1/user", headers)

    if status != 200 or not body.get("id"):
        raise AuthError("Invalid or expired session. Please sign in again.")
    user = User(id=body["id"], email=body.get("email"))
    with _lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (time.monotonic() + CACHE_TTL, user)
    return user


def verify(token: str, fetch=None) -> User:
    if config.SUPABASE_JWT_SECRET and token_alg(token) == "HS256":
        return verify_hs256(token, config.SUPABASE_JWT_SECRET)
    return verify_remote(token, fetch)
