"""Prove that the authenticator binds the payload and its protocol context."""

import secrets
from uuid import uuid4

import pytest

from qkdsim.auth.channel import AuthenticatedChannel, AuthenticationError


def _pair() -> tuple[AuthenticatedChannel, AuthenticatedChannel]:
    key, session = secrets.token_bytes(32), uuid4()
    return (
        AuthenticatedChannel(key, session, "alice"),
        AuthenticatedChannel(key, session, "bob"),
    )


def test_bidirectional_round_trip_and_receive_order() -> None:
    alice, bob = _pair()
    first = alice.seal("bases", b"\x00\x01")
    second = alice.seal("sample", b"")
    assert alice.open("detected", bob.seal("detected", b"gates")) == b"gates"
    with pytest.raises(AuthenticationError, match="out-of-order"):
        bob.open("sample", second)
    assert bob.open("bases", first) == b"\x00\x01"
    with pytest.raises(AuthenticationError, match="replayed"):
        bob.open("bases", first)
    assert bob.open("sample", second) == b""


def test_tampering_and_truncation_do_not_advance_the_receive_counter() -> None:
    alice, bob = _pair()
    frame = alice.seal("bases", b"public bases")
    for where in (0, 16, -34, -1):
        altered = bytearray(frame)
        altered[where] ^= 1
        with pytest.raises(AuthenticationError, match="tag mismatch"):
            bob.open("bases", bytes(altered))
    with pytest.raises(AuthenticationError, match="truncated"):
        bob.open("bases", frame[:4])
    with pytest.raises(AuthenticationError, match="tag mismatch"):
        bob.open("bases", frame[:-1])
    assert bob.open("bases", frame) == b"public bases"


def test_authentication_binds_key_session_sender_and_type() -> None:
    key, session = secrets.token_bytes(32), uuid4()
    alice = AuthenticatedChannel(key, session, "alice")
    bob = AuthenticatedChannel(key, session, "bob")
    frame = alice.seal("permutation", b"order")
    wrong_key = AuthenticatedChannel(secrets.token_bytes(32), session, "bob")
    with pytest.raises(AuthenticationError, match="tag mismatch"):
        wrong_key.open("permutation", frame)
    wrong_session = AuthenticatedChannel(key, uuid4(), "bob")
    with pytest.raises(AuthenticationError, match="session or sender"):
        wrong_session.open("permutation", frame)
    with pytest.raises(AuthenticationError, match="session or sender"):
        alice.open("permutation", frame)
    with pytest.raises(AuthenticationError, match="message kind"):
        bob.open("bases", frame)
    assert bob.open("permutation", frame) == b"order"
