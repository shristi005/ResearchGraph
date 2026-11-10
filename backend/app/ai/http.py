"""The only place AI calls touch the network. Pure standard library (urllib): no extra dependency, easy to test."""
import json as _json
import socket
import urllib.error
import urllib.request

from app.ai.errors import MALFORMED, TRANSIENT, ProviderError, classify_status


def _retry_after(headers) -> float | None:
    try:
        v = headers.get("Retry-After")
        return float(v) if v is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def post_json(provider: str, url: str, headers: dict, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=_json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "researchgraph/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        # Only the status goes to users/logs - never the request (document text) or headers (API keys).
        raise ProviderError(provider, classify_status(exc.code), f"{provider} returned HTTP {exc.code}.",
                            retry_after=_retry_after(exc.headers), status=exc.code) from None
    except (socket.timeout, TimeoutError) as exc:
        raise ProviderError(provider, TRANSIENT,
                            f"{provider} timed out.") from exc
    except (urllib.error.URLError, OSError) as exc:
        if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
            raise ProviderError(provider, TRANSIENT,
                                f"{provider} timed out.") from exc
        raise ProviderError(provider, TRANSIENT,
                            f"Could not reach {provider}.") from exc
    try:
        return _json.loads(body)
    except ValueError as exc:
        raise ProviderError(provider, MALFORMED,
                            f"{provider} returned a non-JSON body.") from exc


def get_json(provider: str, url: str, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, method="GET", headers={
                                 "User-Agent": "researchgraph/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise ProviderError(provider, classify_status(exc.code), f"{provider} returned HTTP {exc.code}.",
                            retry_after=_retry_after(exc.headers), status=exc.code) from None
    except (urllib.error.URLError, OSError, socket.timeout) as exc:
        raise ProviderError(provider, TRANSIENT,
                            f"Could not reach {provider}.") from exc
    except ValueError as exc:
        raise ProviderError(provider, MALFORMED,
                            f"{provider} returned a non-JSON body.") from exc


def post_ndjson(provider: str, url: str, headers: dict, payload: dict, idle_timeout: float, total_timeout: float) -> list[dict]:
    """POST and read a newline-delimited-JSON stream (Ollama stream=true). Streaming keeps bytes flowing, so a proxy such as
    Cloudflare (which gives up after ~100 s of silence) does not cut a slow CPU generation. idle_timeout applies to each read."""
    import time as _t
    req = urllib.request.Request(url, data=_json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "researchgraph/1.0", **headers})
    out: list[dict] = []
    start = _t.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=idle_timeout) as r:
            for raw in r:
                if _t.monotonic() - start > total_timeout:
                    raise ProviderError(provider, TRANSIENT,
                                        f"{provider} took too long.")
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(_json.loads(raw))
                except ValueError as exc:
                    raise ProviderError(
                        provider, MALFORMED, f"{provider} sent an unreadable stream.") from exc
    except urllib.error.HTTPError as exc:
        raise ProviderError(provider, classify_status(exc.code), f"{provider} returned HTTP {exc.code}.",
                            retry_after=_retry_after(exc.headers), status=exc.code) from None
    except (socket.timeout, TimeoutError) as exc:
        raise ProviderError(provider, TRANSIENT,
                            f"{provider} timed out.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderError(provider, TRANSIENT,
                            f"Could not reach {provider}.") from exc
    return out
