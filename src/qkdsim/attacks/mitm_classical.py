"""Run the classical impersonation attack on two independent BB84 links."""

import secrets
from dataclasses import dataclass

from numpy.random import Generator

from qkdsim.auth.channel import AUTH_BITS, AuthenticatedChannel, Party
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import SessionConfig
from qkdsim.monitor.session import MonitoredSession
from qkdsim.postprocess.result import AbortEvidence, LinkKeys
from qkdsim.simulation import run_bb84_link


@dataclass(frozen=True)
class MitmResult:
    """Ground-truth comparisons and public reasons, with no key material."""

    alice_key_known_to_eve: bool
    bob_key_known_to_eve: bool
    peer_keys_differ: bool
    alice_abort: str | None
    bob_abort: str | None

    @property
    def succeeded(self) -> bool:
        """Eve succeeded when she established a separate key with each peer."""
        return (
            self.alice_key_known_to_eve
            and self.bob_key_known_to_eve
            and self.peer_keys_differ
        )


def _leg(
    config: SessionConfig,
    rng: Generator,
    eve: Party,
    authentication: AuthenticationPool | None,
) -> tuple[LinkKeys | AbortEvidence, str | None]:
    session = MonitoredSession(config)
    if authentication is None:
        result = run_bb84_link(config, rng, session=session)
    else:
        # Eve substitutes her own signed announcement in the direction she is
        # impersonating. The two honest endpoints expect their pre-shared key.
        imposter = AuthenticatedChannel(
            secrets.token_bytes(AUTH_BITS // 8),
            session.session_id,
            eve,
        )

        def substitute(sender: Party, kind: str, frame: bytes) -> bytes:
            if sender == eve:
                return imposter.seal(kind, b"Eve's substituted announcement")
            return frame

        result = run_bb84_link(
            config,
            rng,
            session=session,
            authentication=authentication,
            transport=substitute,
        )
    return result, session.events[-1].reason if isinstance(
        result, AbortEvidence
    ) else None


def run_classical_mitm(
    config: SessionConfig,
    rng: Generator,
    *,
    authenticated: bool,
) -> MitmResult:
    """Let Eve act as Bob to Alice and Alice to Bob, using separate pulse draws."""
    authentication = AuthenticationPool() if authenticated else None
    alice_link, alice_abort = _leg(config, rng, "bob", authentication)
    bob_link, bob_abort = _leg(config, rng, "alice", authentication)
    # Eve holds the independently amplified Bob output on Alice's link and the
    # independently amplified Alice output on Bob's link.
    alice_known = isinstance(alice_link, LinkKeys) and secrets.compare_digest(
        alice_link.alice.key_bytes,
        alice_link.bob_bytes,
    )
    bob_known = isinstance(bob_link, LinkKeys) and secrets.compare_digest(
        bob_link.bob_bytes,
        bob_link.alice.key_bytes,
    )
    differ = (
        isinstance(alice_link, LinkKeys)
        and isinstance(bob_link, LinkKeys)
        and not secrets.compare_digest(alice_link.alice.key_bytes, bob_link.bob_bytes)
    )
    return MitmResult(alice_known, bob_known, differ, alice_abort, bob_abort)
