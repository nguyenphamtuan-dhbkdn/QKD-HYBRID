"""Binary framing and HMAC-SHA256 authentication for a pair of endpoints."""

import hmac
from collections.abc import Callable
from struct import Struct
from threading import Lock
from typing import Literal
from uuid import UUID

Party = Literal["alice", "bob"]
Transport = Callable[[Party, str, bytes], bytes]

_HEADER = Struct("!4s16sBQBI")
_MAGIC = b"QKD1"
_TAG_SIZE = 32
AUTH_BITS = 256


class AuthenticationError(ValueError):
    """An incoming classical frame failed validation."""


class AuthenticatedChannel:
    """One endpoint with independent, strictly ordered send/receive counters."""

    def __init__(self, key: bytes, session_id: UUID, party: Party) -> None:
        if type(key) is not bytes or len(key) != AUTH_BITS // 8:
            raise ValueError("HMAC requires a 256-bit pre-shared key")
        if party not in ("alice", "bob"):
            raise ValueError("party must be alice or bob")
        self._key = key
        self._session = session_id.bytes
        self._direction = 0 if party == "alice" else 1
        self._sent = 0
        self._received = 0
        self._lock = Lock()

    def seal(self, kind: str, payload: bytes) -> bytes:
        """Encode header || kind || payload || HMAC-SHA256(key, encoded body)."""
        label = kind.encode("ascii")
        if not 1 <= len(label) <= 255 or len(payload) >= 1 << 32:
            raise ValueError("invalid classical message kind or payload length")
        with self._lock:
            if self._sent >= 1 << 64:
                raise AuthenticationError("send counter exhausted")
            header = _HEADER.pack(
                _MAGIC,
                self._session,
                self._direction,
                self._sent,
                len(label),
                len(payload),
            )
            body = header + label + payload
            tag = hmac.digest(self._key, body, "sha256")
            self._sent += 1
            return body + tag

    def open(self, kind: str, frame: bytes) -> bytes:
        """Check tag, framing, session, direction, type, and the expected counter."""
        if len(frame) < _HEADER.size + _TAG_SIZE + 1:
            raise AuthenticationError("truncated classical frame")
        body, tag = frame[:-_TAG_SIZE], frame[-_TAG_SIZE:]
        if not hmac.compare_digest(tag, hmac.digest(self._key, body, "sha256")):
            raise AuthenticationError("authentication tag mismatch")
        magic, session, direction, counter, label_size, size = _HEADER.unpack_from(body)
        end_label = _HEADER.size + label_size
        if magic != _MAGIC or not label_size or len(body) != end_label + size:
            raise AuthenticationError("invalid classical frame")
        if session != self._session or direction != 1 - self._direction:
            raise AuthenticationError("unexpected session or sender")
        if body[_HEADER.size : end_label] != kind.encode("ascii"):
            raise AuthenticationError("unexpected classical message kind")
        with self._lock:
            if counter != self._received:
                raise AuthenticationError("replayed or out-of-order classical frame")
            self._received += 1
        return body[end_label:]


class ClassicalLink:
    """An in-process bidirectional public transport between two endpoints."""

    def __init__(
        self,
        key: bytes,
        session_id: UUID,
        transport: Transport | None = None,
    ) -> None:
        self._alice = AuthenticatedChannel(key, session_id, "alice")
        self._bob = AuthenticatedChannel(key, session_id, "bob")
        self._transport = transport

    def exchange(self, sender: Party, kind: str, payload: bytes) -> bytes:
        """Deliver an authenticated message, optionally through an Eve proxy."""
        source, target = (
            (self._alice, self._bob) if sender == "alice" else (self._bob, self._alice)
        )
        frame = source.seal(kind, payload)
        if self._transport is not None:
            frame = self._transport(sender, kind, frame)
        accepted = target.open(kind, frame)
        # The simulator shares one transcript object. Refuse an inconsistent
        # authenticated replacement before consuming any data from it.
        if accepted != payload:
            raise AuthenticationError("authenticated transcript mismatch")
        return accepted
