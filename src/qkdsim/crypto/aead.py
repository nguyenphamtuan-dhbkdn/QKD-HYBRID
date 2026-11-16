"""AEAD primitives and nonce allocation for high-level encryption."""

from secrets import token_bytes
from threading import Lock
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers.aead import (
    ChaCha20Poly1305 as _LibraryChaCha20Poly1305,
)

from qkdsim.crypto.kdf import KEY_SIZE

NONCE_PREFIX_SIZE = 4
COUNTER_SIZE = 8
NONCE_SIZE = NONCE_PREFIX_SIZE + COUNTER_SIZE
TAG_SIZE = 16
MAX_MESSAGES = 1 << 32
DEFAULT_MAX_MESSAGES = 1 << 20


class NonceExhaustedError(RuntimeError):
    """The encryption key's nonce budget has been spent."""


class NonceSequence:
    """Allocate nonce = random 32-bit prefix || big-endian 64-bit counter.

    Use one sequence per AEAD key and share it across that key's encryptions.
    """

    def __init__(self, max_messages: int = DEFAULT_MAX_MESSAGES) -> None:
        if type(max_messages) is not int or not 1 <= max_messages <= MAX_MESSAGES:
            raise ValueError("nonce limit must be in [1, 2**32]")
        self._prefix = token_bytes(NONCE_PREFIX_SIZE)
        self._max_messages = max_messages
        self._counter = 0
        self._lock = Lock()

    @property
    def prefix(self) -> bytes:
        """Return the public nonce prefix."""
        return self._prefix

    def next_nonce(self) -> bytes:
        """Burn the next counter at allocation time and refuse to wrap."""
        with self._lock:
            if self._counter >= self._max_messages:
                raise NonceExhaustedError("per-key message limit exceeded")
            nonce = self._prefix + self._counter.to_bytes(COUNTER_SIZE, "big")
            self._counter += 1
        return nonce


class Aead(Protocol):
    """Low-level AEAD interface for an explicit key, nonce and associated data."""

    name: str
    key_size: int
    nonce_size: int
    tag_size: int

    def encrypt(self, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        """Return ciphertext || authentication tag."""
        ...

    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        """Verify the tag against the ciphertext and AAD before returning plaintext."""
        ...


class _LibraryAead:
    """Enforce the sizes shared by both library AEADs."""

    name: str
    key_size = KEY_SIZE
    nonce_size = NONCE_SIZE
    tag_size = TAG_SIZE
    _algorithm: type[AESGCM] | type[_LibraryChaCha20Poly1305]

    def _cipher(self, key: bytes, nonce: bytes) -> AESGCM | _LibraryChaCha20Poly1305:
        if len(key) != self.key_size:
            raise ValueError("AEAD requires a 32-byte key")
        if len(nonce) != self.nonce_size:
            raise ValueError("AEAD requires a 12-byte nonce")
        return self._algorithm(key)

    def encrypt(self, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        """Seal plaintext as ciphertext || 128-bit tag with the supplied nonce."""
        return self._cipher(key, nonce).encrypt(nonce, plaintext, aad)

    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        """Open ciphertext || tag, propagating InvalidTag on authentication failure."""
        return self._cipher(key, nonce).decrypt(nonce, ciphertext, aad)


class AesGcm256(_LibraryAead):
    """AES-256 in GCM mode with a 96-bit nonce and a 128-bit tag."""

    name = "aes256gcm"
    _algorithm = AESGCM


class ChaCha20Poly1305(_LibraryAead):
    """RFC 8439 ChaCha20-Poly1305 with a 96-bit nonce and a 128-bit tag."""

    name = "chacha20poly1305"
    _algorithm = _LibraryChaCha20Poly1305
