"""Encryption of stored tokens and signing of the OAuth `state` parameter."""
import base64
import hashlib
import hmac
import secrets
import time

from cryptography.fernet import Fernet


def encrypt(key: str, plaintext: str) -> bytes:
    return Fernet(key.encode()).encrypt(plaintext.encode())


def decrypt(key: str, token: bytes) -> str:
    return Fernet(key.encode()).decrypt(bytes(token)).decode()


def _state_key(key: str) -> bytes:
    # Derive a separate signing key so the encryption key is never used directly for HMAC.
    return hmac.new(key.encode(), b"oauth-state-v1", hashlib.sha256).digest()


def sign_state(key: str, now: int | None = None) -> str:
    """Return a CSRF-protection value: nonce.timestamp.signature"""
    ts = str(now if now is not None else int(time.time()))
    nonce = secrets.token_urlsafe(16)
    payload = f"{nonce}.{ts}"
    sig = hmac.new(_state_key(key), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def verify_state(key: str, state: str, max_age_s: int = 600, now: int | None = None) -> bool:
    try:
        nonce, ts, sig = state.split(".")
    except ValueError:
        return False
    expected = hmac.new(_state_key(key), f"{nonce}.{ts}".encode(), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).decode().rstrip("=")
    if not hmac.compare_digest(expected_b64, sig):
        return False
    current = now if now is not None else int(time.time())
    return ts.isdigit() and 0 <= current - int(ts) <= max_age_s


def constant_time_equals(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())
