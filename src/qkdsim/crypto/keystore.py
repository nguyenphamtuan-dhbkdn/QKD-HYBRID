"""In-memory, ETSI-style key delivery for two simulated peers."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isfinite
from threading import Lock
from uuid import UUID

from qkdsim.config import MonitorConfig
from qkdsim.postprocess.result import FinalKey


class KeyStatus(StrEnum):
    """An entry's delivery state."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    USED = "used"
    REVOKED = "revoked"


class KeyUnavailableError(LookupError):
    """There is no eligible key for this delivery operation."""


@dataclass
class _Entry:
    key: FinalKey | None = field(repr=False)
    expires_at: datetime
    status: KeyStatus = KeyStatus.AVAILABLE

    def expire(self, now: datetime) -> None:
        if self.key is not None and now >= self.expires_at:
            self.retire(KeyStatus.REVOKED)

    def retire(self, status: KeyStatus) -> None:
        self.key = None
        self.status = status


class KeyStore:
    """Reserve the oldest eligible whole FinalKey, then deliver it by UUID4.

    TTL starts at FinalKey.created_at. Retired entries retain IDs to prevent
    reuse within the lifetime of the store.
    """

    def __init__(self, ttl_seconds: float = MonitorConfig().max_seconds) -> None:
        if not isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("key TTL must be positive and finite")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._entries: dict[UUID, _Entry] = {}
        self._lock = Lock()

    def add_key(self, key: FinalKey) -> None:
        """Add a final key to the end of the FIFO, preserving its existing ID."""
        if key.key_id.version != 4:
            raise ValueError("key ID must be a UUID4")
        if key.length_bits < 1 or len(key.key_bytes) != (key.length_bits + 7) // 8:
            raise ValueError("key length does not match the packed key")
        if key.created_at.utcoffset() is None:
            raise ValueError("key creation time must include a timezone")
        with self._lock:
            if key.key_id in self._entries:
                raise ValueError("key ID already exists")
            entry = _Entry(key, key.created_at.astimezone(UTC) + self._ttl)
            entry.expire(datetime.now(UTC))
            self._entries[key.key_id] = entry

    def get_status(self) -> dict[KeyStatus, int]:
        """Report the count of entries in each state, without key material."""
        counts = {status: 0 for status in KeyStatus}
        with self._lock:
            now = datetime.now(UTC)
            for entry in self._entries.values():
                entry.expire(now)
                counts[entry.status] += 1
        return counts

    def get_key(self, size: int) -> FinalKey:
        """Reserve the first available key with at least size bits."""
        if type(size) is not int or size < 1:
            raise ValueError("requested key size in bits must be positive")
        with self._lock:
            now = datetime.now(UTC)
            for entry in self._entries.values():
                entry.expire(now)
                key = entry.key
                if (
                    entry.status == KeyStatus.AVAILABLE
                    and key is not None
                    and key.length_bits >= size
                ):
                    entry.status = KeyStatus.RESERVED
                    return key
        raise KeyUnavailableError("no available key meets the requested size")

    def get_key_with_id(self, key_id: UUID | bytes) -> FinalKey:
        """Deliver a reserved key once and mark it used."""
        if isinstance(key_id, bytes):
            key_id = UUID(bytes=key_id)
        with self._lock:
            entry = self._lookup(key_id)
            key = entry.key
            if entry.status != KeyStatus.RESERVED or key is None:
                raise KeyUnavailableError("key is not reserved for delivery")
            entry.retire(KeyStatus.USED)
            return key

    def revoke(self, key_id: UUID) -> None:
        """Retire an undelivered key, including any outstanding reservation."""
        with self._lock:
            entry = self._lookup(key_id)
            if entry.status == KeyStatus.USED:
                raise KeyUnavailableError("key has already been delivered")
            entry.retire(KeyStatus.REVOKED)

    def _lookup(self, key_id: UUID) -> _Entry:
        entry = self._entries.get(key_id)
        if entry is None:
            raise KeyUnavailableError("unknown key ID")
        entry.expire(datetime.now(UTC))
        return entry
