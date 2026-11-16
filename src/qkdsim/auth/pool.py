"""Reserve one HMAC key per link and rotate it with fresh BB84 key bits."""

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from uuid import UUID

from qkdsim.auth.channel import AUTH_BITS, ClassicalLink, Transport


class AuthenticationPool:
    """Keep the pre-shared key across sessions and rotate it after success."""

    def __init__(self, initial_key: bytes | None = None) -> None:
        if initial_key is None:
            initial_key = secrets.token_bytes(AUTH_BITS // 8)
        if type(initial_key) is not bytes or len(initial_key) != AUTH_BITS // 8:
            raise ValueError("the initial authentication key must have 256 bits")
        self._key = initial_key
        self._lock = Lock()
        self._rotations = 0

    @property
    def rotations(self) -> int:
        """Return the number of successful authentication-key refreshes."""
        with self._lock:
            return self._rotations

    @contextmanager
    def link(
        self,
        session_id: UUID,
        transport: Transport | None = None,
    ) -> Iterator[tuple[ClassicalLink, Callable[[bytes], None]]]:
        """Hold the pool through a session and provide a one-use refresh operation."""
        with self._lock:
            active = True
            refreshed = False

            def refresh(prefix: bytes) -> None:
                nonlocal refreshed
                if not active or refreshed:
                    raise RuntimeError("authentication-key refresh unavailable")
                if type(prefix) is not bytes or len(prefix) != AUTH_BITS // 8:
                    raise ValueError("authentication refresh requires 256 bits")
                self._key = prefix
                self._rotations += 1
                refreshed = True

            try:
                yield ClassicalLink(self._key, session_id, transport), refresh
            finally:
                active = False
