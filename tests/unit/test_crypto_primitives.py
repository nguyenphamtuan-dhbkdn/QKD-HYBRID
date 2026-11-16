"""Published vectors and invariants for key derivation and nonce allocation."""

import re
from concurrent.futures import ThreadPoolExecutor
from hmac import digest
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from hypothesis import given, settings
from hypothesis import strategies as st

from qkdsim.crypto.aead import (
    MAX_MESSAGES,
    Aead,
    AesGcm256,
    ChaCha20Poly1305,
    NonceExhaustedError,
    NonceSequence,
)
from qkdsim.crypto.kdf import _hkdf_sha256, derive_keys


def test_crypto_uses_os_entropy_and_does_not_log_key_material() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "qkdsim" / "crypto"
    source = "\n".join(
        module.read_text(encoding="utf-8") for module in package.glob("*.py")
    )
    assert re.search(r"^from secrets import token_bytes$", source, re.MULTILINE)
    assert re.search(r"\b(?:qkdsim\.rng|numpy|SimRNG)\b", source) is None
    assert (
        re.search(
            r"\b(?:print|debug|info|warning|error|critical|exception|log)\([^)]*"
            r"\b(?:key|key_bytes|final_key|material|derived_key|aead_key)\b",
            source,
        )
        is None
    )


def test_hkdf_rfc_5869_case_1() -> None:
    # https://www.rfc-editor.org/rfc/rfc5869.html#appendix-A.1
    expected = bytes.fromhex(
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )
    assert (
        _hkdf_sha256(b"\x0b" * 22, bytes(range(13)), bytes(range(0xF0, 0xFA)), 42)
        == expected
    )


@given(
    key=st.binary(min_size=32, max_size=128), salt=st.binary(min_size=16, max_size=16)
)
def test_derive_keys_matches_labeled_hkdf_and_separates_domains(
    key: bytes, salt: bytes
) -> None:
    labels = ("aes256gcm", "chacha20poly1305", "auth", "otp")
    keys = derive_keys(key, salt, labels)
    assert derive_keys(key, salt, labels[::-1]) == keys
    assert len(set(keys.values())) == len(labels)
    assert keys != derive_keys(key, salt + b"\x01", labels)

    prk = digest(salt, key, "sha256")
    for label, derived_key in keys.items():
        # A 32-byte output requires only T(1) = HMAC(PRK, info || 0x01).
        info = f"qkd-hybrid/v1/{label}".encode()
        assert derived_key == digest(prk, info + b"\x01", "sha256")


@pytest.mark.parametrize(
    ("key", "salt", "labels", "error"),
    [
        (bytes(31), bytes(16), ("auth",), "32 bytes"),
        (bytes(32), b"", ("auth",), "salt"),
        (bytes(32), bytes(16), ("unknown",), "label"),
    ],
)
def test_derive_keys_rejects_invalid_inputs(
    key: bytes, salt: bytes, labels: tuple[str, ...], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        derive_keys(key, salt, labels)


def test_aes256gcm_nist_example_4() -> None:
    # NIST CSRC AES_GCM.pdf, GCM-AES256 Example #4.
    key = bytes.fromhex("feffe9928665731c6d6a8f9467308308") * 2
    nonce = bytes.fromhex("cafebabefacedbaddecaf888")
    aad = bytes.fromhex(
        "3ad77bb40d7a3660a89ecaf32466ef97 f5d3d58503b9699de785895a96fdbaaf "
        "43b1cd7f598ece23881b00e3ed030688 7b0c785e27e8ad3f8223207104725dd4"
    )
    plaintext = bytes.fromhex(
        "d9313225f88406e5a55909c5aff5269a 86a7a9531534f7da2e4c303d8a318a72 "
        "1c3c0c95956809532fcf0e2449a6b525 b16aedf5aa0de657ba637b391aafd255"
    )
    sealed = bytes.fromhex(
        "522DC1F0 99567D07 F47F37A3 2A84427D "
        "643A8CDC BFE5C0C9 7598A2BD 2555D1AA "
        "8CB08E48 590DBB3D A7B08B10 56828838 "
        "C5F61E63 93BA7A0A BCC9F662 898015AD "
        "C06D76F3 1930FEF3 7ACAE23E D465AE62"
    )
    aead = AesGcm256()
    assert aead.encrypt(key, nonce, plaintext, aad) == sealed
    assert aead.decrypt(key, nonce, sealed, aad) == plaintext


def test_chacha20poly1305_rfc_8439() -> None:
    # https://www.rfc-editor.org/rfc/rfc8439.html#section-2.8.2
    key = bytes(range(0x80, 0xA0))
    nonce = bytes.fromhex("070000004041424344454647")
    aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
    plaintext = bytes.fromhex(
        "4c616469657320616e642047656e746c 656d656e206f662074686520636c6173 "
        "73206f66202739393a20496620492063 6f756c64206f6666657220796f75206f "
        "6e6c79206f6e652074697020666f7220 746865206675747572652c2073756e73 "
        "637265656e20776f756c642062652069 742e"
    )
    sealed = bytes.fromhex(
        "d31a8d34648e60db7b86afbc53ef7ec2 a4aded51296e08fea9e2b5a736ee62d6 "
        "3dbea45e8ca9671282fafb69da92728b 1a71de0a9e060b2905d6a5b67ecd3b36 "
        "92ddbd7f2d778b8c9803aee328091b58 fab324e4fad675945585808b4831d7bc "
        "3ff4def08e4b7a9de576d26586cec64b 6116 1ae10b594f09e26a7e902ecbd0600691"
    )
    aead = ChaCha20Poly1305()
    assert aead.encrypt(key, nonce, plaintext, aad) == sealed
    assert aead.decrypt(key, nonce, sealed, aad) == plaintext


@pytest.mark.parametrize("aead", [AesGcm256(), ChaCha20Poly1305()])
def test_aead_rejects_wrong_aad_key_nonce_and_tag(aead: Aead) -> None:
    key, nonce, aad = bytes(32), bytes(12), b"test context"
    sealed = aead.encrypt(key, nonce, b"data", aad)
    with pytest.raises(InvalidTag):
        aead.decrypt(key, nonce, sealed, b"wrong context")
    with pytest.raises(InvalidTag):
        aead.decrypt(b"\x01" * 32, nonce, sealed, aad)
    with pytest.raises(InvalidTag):
        aead.decrypt(key, b"\x01" * 12, sealed, aad)
    with pytest.raises(InvalidTag):
        aead.decrypt(key, nonce, sealed[:-1], aad)

    with pytest.raises(ValueError, match="32-byte"):
        aead.encrypt(bytes(16), nonce, b"data", aad)
    with pytest.raises(ValueError, match="12-byte"):
        aead.decrypt(key, bytes(13), sealed, aad)


@settings(max_examples=6, deadline=None)
@given(count=st.integers(min_value=100_000, max_value=105_000))
def test_nonce_uniqueness_and_exhaustion(count: int) -> None:
    allocator = NonceSequence(max_messages=count)
    nonces = set()
    for counter in range(count):
        nonce = allocator.next_nonce()
        assert nonce == allocator.prefix + counter.to_bytes(8, "big")
        assert len(nonce) == 12
        nonces.add(nonce)
    assert len(nonces) == count
    for _ in range(2):
        with pytest.raises(NonceExhaustedError):
            allocator.next_nonce()


def test_nonce_hard_cap_and_concurrent_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="nonce limit"):
        NonceSequence(MAX_MESSAGES + 1)
    allocator = NonceSequence(MAX_MESSAGES)
    monkeypatch.setattr(allocator, "_counter", MAX_MESSAGES - 128)

    def allocate(_: int) -> bytes:
        return allocator.next_nonce()

    with ThreadPoolExecutor(max_workers=8) as executor:
        allocated = set(executor.map(allocate, range(128)))
    assert len(allocated) == 128
    assert max(allocated) == allocator.prefix + (MAX_MESSAGES - 1).to_bytes(8, "big")
    with pytest.raises(NonceExhaustedError):
        allocator.next_nonce()
