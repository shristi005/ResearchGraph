import hashlib


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def looks_like_pdf(data: bytes) -> bool:
    # PDF spec allows a few bytes of junk before the header; check first 1KB.
    return b"%PDF-" in data[:1024]
