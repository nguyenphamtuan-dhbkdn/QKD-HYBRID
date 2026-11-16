"""FIFO selection, one-time delivery, expiration, and revocation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo
from uuid import uuid1, uuid4

import pytest

from qkdsim.crypto import keystore
from qkdsim.crypto.keystore import KeyStatus, KeyStore, KeyUnavailableError
from qkdsim.postprocess.result import FinalKey


def _final_key(bits: int = 256) -> FinalKey:
    return FinalKey(
        key_bytes=b"\xa5" * ((bits + 7) // 8),
        key_id=uuid4(),
        session_id=uuid4(),
        length_bits=bits,
        qber=0,
        qber_ub=0.04,
        leak_total=64,
        eps_sec=1e-9,
        eps_cor=1e-12,
        created_at=datetime.now(UTC),
        backend="fast",
        ground_truth_eve_present=False,
    )


def test_store_reserves_oldest_eligible_key_then_delivers_once() -> None:
    pool = KeyStore()
    small, first, second = _final_key(128), _final_key(384), _final_key()
    for key in (small, first, second):
        pool.add_key(key)
    with pytest.raises(KeyUnavailableError):
        pool.get_key_with_id(first.key_id)

    assert pool.get_key(256) is first
    assert pool.get_key(256) is second
    assert pool.get_status() == {
        KeyStatus.AVAILABLE: 1,
        KeyStatus.RESERVED: 2,
        KeyStatus.USED: 0,
        KeyStatus.REVOKED: 0,
    }
    with pytest.raises(KeyUnavailableError):
        pool.get_key(256)
    assert pool.get_key(128) is small
    assert pool.get_key_with_id(first.key_id.bytes) is first
    assert pool.get_status()[KeyStatus.USED] == 1
    assert pool.get_status()[KeyStatus.RESERVED] == 2
    with pytest.raises(KeyUnavailableError):
        pool.get_key_with_id(first.key_id)
    with pytest.raises(KeyUnavailableError):
        pool.revoke(first.key_id)

    with pytest.raises(ValueError, match="already exists"):
        pool.add_key(first)
    assert repr(first.key_bytes) not in repr(pool)


def test_store_ttl_and_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = KeyStore(ttl_seconds=10)
    reserved = _final_key()
    expires_at = reserved.created_at + timedelta(seconds=10)
    revocable = _final_key()
    expired_at_intake = replace(
        _final_key(), created_at=reserved.created_at - timedelta(minutes=1)
    )
    for key in (reserved, revocable, expired_at_intake):
        pool.add_key(key)
    assert pool.get_status()[KeyStatus.REVOKED] == 1
    assert pool.get_key(256) is reserved
    pool.revoke(revocable.key_id)
    pool.revoke(revocable.key_id)
    with pytest.raises(KeyUnavailableError):
        pool.revoke(uuid4())
    assert pool.get_status()[KeyStatus.REVOKED] == 2

    class AtExpiry(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return expires_at

    monkeypatch.setattr(keystore, "datetime", AtExpiry)
    with pytest.raises(KeyUnavailableError):
        pool.get_key_with_id(reserved.key_id)
    assert pool.get_status()[KeyStatus.REVOKED] == 3


def test_store_rejects_invalid_intake_and_request() -> None:
    for ttl in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="TTL"):
            KeyStore(ttl_seconds=ttl)
    pool = KeyStore()
    key = _final_key()
    for invalid_key in (
        replace(key, key_id=uuid1()),
        replace(key, length_bits=7),
        replace(key, created_at=key.created_at.replace(tzinfo=None)),
    ):
        with pytest.raises(ValueError):
            pool.add_key(invalid_key)
    for size in (0, -1, True):
        with pytest.raises(ValueError, match="size in bits"):
            pool.get_key(size)


def test_store_reservation_and_delivery_are_thread_safe() -> None:
    key = _final_key()
    pool = KeyStore()
    pool.add_key(key)

    def reserve(_: int) -> FinalKey | None:
        try:
            return pool.get_key(256)
        except KeyUnavailableError:
            return None

    def deliver(_: int) -> FinalKey | None:
        try:
            return pool.get_key_with_id(key.key_id)
        except KeyUnavailableError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        reservations = list(executor.map(reserve, range(16)))
        deliveries = list(executor.map(deliver, range(16)))
    assert [reserved for reserved in reservations if reserved is not None] == [key]
    assert [used for used in deliveries if used is not None] == [key]
