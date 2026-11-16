"""HKDF-SHA256 with separate labels for each use of QKD key material."""

from collections.abc import Sequence

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_LABELS = {
    "aes256gcm": b"qkd-hybrid/v1/aes256gcm",
    "chacha20poly1305": b"qkd-hybrid/v1/chacha20poly1305",
    "auth": b"qkd-hybrid/v1/auth",
    "otp": b"qkd-hybrid/v1/otp",
}
KEY_SIZE = 32


def _hkdf_sha256(material: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Compute OKM = HKDF-Expand(HMAC-SHA256(salt, material), info, length)."""
    return HKDF(algorithm=SHA256(), length=length, salt=salt, info=info).derive(
        material
    )


def derive_keys(
    final_key: bytes, salt: bytes, ciphers: Sequence[str]
) -> dict[str, bytes]:
    """Derive one 256-bit key per label from at least 32 bytes of QKD material.

    The salt is public. HKDF does not make keys from seeded simulations secure.
    """
    if len(final_key) < KEY_SIZE:
        raise ValueError("at least 32 bytes of QKD key material are required")
    if not salt:
        raise ValueError("HKDF salt must not be empty")

    keys = {}
    for cipher in ciphers:
        if cipher not in _LABELS:
            raise ValueError("unknown key derivation label")
        keys[cipher] = _hkdf_sha256(final_key, salt, _LABELS[cipher], KEY_SIZE)
    return keys
