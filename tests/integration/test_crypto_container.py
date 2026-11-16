"""QKDH v1 integration and adversarial file tests for both ciphers."""

import tracemalloc
from dataclasses import replace
from hashlib import file_digest
from pathlib import Path
from random import Random
from struct import Struct, pack
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from hypothesis import example, given, settings
from hypothesis import strategies as st

from qkdsim.config import BB84Config, ChannelConfig, SessionConfig
from qkdsim.crypto.aead import Aead, AesGcm256, ChaCha20Poly1305, NonceExhaustedError
from qkdsim.crypto.container import (
    MAX_CHUNK_SIZE,
    ContainerError,
    SessionMeta,
    decrypt_file,
    encrypt_file,
)
from qkdsim.crypto.kdf import derive_keys
from qkdsim.crypto.keystore import KeyStatus, KeyStore, KeyUnavailableError
from qkdsim.postprocess.result import LinkKeys
from qkdsim.simulation import run_bb84_link

_CIPHERS = (AesGcm256(), ChaCha20Poly1305())
_HEADER = Struct(">4sBB16s16s16s4sIQ")
_KEY = bytes(range(32))
_MIB = 1024**2


def _lookup_fixture_key(_: bytes) -> bytes:
    return _KEY


def test_simulated_link_key_can_seal_and_open_a_file(tmp_path: Path) -> None:
    config = SessionConfig(
        bb84=BB84Config(
            n_pulses=8192,
            p_z=1,
            test_fraction=0.25,
            eps_pe=0.01,
            ec_mode="ideal",
        ),
        channel=ChannelConfig(e_misalign=0),
    )
    link = run_bb84_link(config)
    assert isinstance(link, LinkKeys)
    pool = KeyStore()
    pool.add_key(replace(link.alice, key_bytes=link.bob_bytes))
    reserved = pool.get_key(256)
    sender = link.alice
    meta = SessionMeta(sender.session_id, reserved.key_id)
    source, sealed, opened = (
        tmp_path / name for name in ("source", "sealed", "opened")
    )
    source.write_bytes(b"simulated QKD payload")
    encrypt_file(source, sealed, config.crypto.cipher, sender.key_bytes, meta)
    receiver = pool.get_key_with_id(reserved.key_id)

    def provide(key_id: bytes) -> bytes:
        if key_id != receiver.key_id.bytes:
            raise KeyUnavailableError("unknown key ID")
        return receiver.key_bytes

    decrypt_file(sealed, opened, provide)
    assert opened.read_bytes() == source.read_bytes()
    assert pool.get_status()[KeyStatus.USED] == 1


@pytest.mark.parametrize("aead", _CIPHERS)
@settings(max_examples=16, deadline=None)
@given(size=st.integers(min_value=0, max_value=5 * _MIB))
@example(size=0)
@example(size=1)
@example(size=65_535)
@example(size=65_536)
@example(size=65_537)
@example(size=5 * _MIB)
def test_random_size_round_trip(aead: Aead, size: int) -> None:
    data = Random(size).randbytes(size)
    meta = SessionMeta(uuid4(), uuid4())

    def provide(key_id: bytes) -> bytes:
        assert key_id == meta.key_id.bytes
        return _KEY

    with TemporaryDirectory() as folder:
        source = Path(folder) / "source"
        sealed = Path(folder) / "sealed"
        opened = Path(folder) / "opened"
        source.write_bytes(data)
        report = encrypt_file(source, sealed, aead.name, _KEY, meta)
        verified = decrypt_file(sealed, opened, provide)
        assert opened.read_bytes() == data
        assert verified.session_meta == report.session_meta == meta
        assert verified.cipher == report.cipher == aead.name
        assert verified.plaintext_bytes == report.plaintext_bytes == size
        assert (
            verified.container_bytes == report.container_bytes == sealed.stat().st_size
        )
        assert verified.chunks == report.chunks == max(1, (size + 65_535) // 65_536)


@pytest.mark.parametrize("aead", _CIPHERS)
def test_container_rejects_tamper_truncation_and_replay_of_chunks(
    tmp_path: Path, aead: Aead
) -> None:
    source, sealed, opened = (
        tmp_path / name for name in ("source", "sealed", "opened")
    )
    source.write_bytes(b"first---second--last")
    meta = SessionMeta(uuid4(), uuid4())
    encrypt_file(source, sealed, aead.name, _KEY, meta, chunk_size=8)
    data = sealed.read_bytes()
    header, chunks = data[: _HEADER.size], data[_HEADER.size :]
    chunk_wire_size = 8 + 8 + 16
    first = chunks[:chunk_wire_size]
    second = chunks[chunk_wire_size : 2 * chunk_wire_size]
    final = chunks[2 * chunk_wire_size :]
    opened.write_bytes(b"previous output")

    for position in range(len(data)):
        mutated = data[:position] + bytes([data[position] ^ 1]) + data[position + 1 :]
        sealed.write_bytes(mutated)
        with pytest.raises((ContainerError, InvalidTag)):
            decrypt_file(sealed, opened, _lookup_fixture_key)
    for cut in range(len(data)):
        sealed.write_bytes(data[:cut])
        with pytest.raises(ContainerError):
            decrypt_file(sealed, opened, _lookup_fixture_key)
    for invalid_chunks in (
        second + first + final,
        first + first + final,
        first + second + final + b"trailer",
        # Renumbering reordered ciphertext fails authentication at the first chunk.
        first[:8] + second[8:] + second[:8] + first[8:] + final,
    ):
        sealed.write_bytes(header + invalid_chunks)
        with pytest.raises((ContainerError, InvalidTag)):
            decrypt_file(sealed, opened, _lookup_fixture_key)

    sealed.write_bytes(data)
    with pytest.raises(InvalidTag):
        decrypt_file(sealed, opened, lambda _: b"\xff" * 32)
    assert opened.read_bytes() == b"previous output"
    assert set(tmp_path.iterdir()) == {source, sealed, opened}


@pytest.mark.parametrize(("cipher_id", "aead"), enumerate(_CIPHERS, start=1))
def test_wire_encoding_binds_header_sequence_index_and_final_flag(
    tmp_path: Path, cipher_id: int, aead: Aead
) -> None:
    source, sealed = (tmp_path / name for name in ("source", "sealed"))
    meta = SessionMeta(uuid4(), uuid4())
    source.write_bytes(b"abc")
    encrypt_file(source, sealed, aead.name, _KEY, meta, chunk_size=2)
    data = sealed.read_bytes()
    header = data[: _HEADER.size]
    magic, version, cipher, session, key_id, salt, prefix, size, total = _HEADER.unpack(
        header
    )
    assert (magic, version, cipher, size, total) == (b"QKDH", 1, cipher_id, 2, 3)
    assert (session, key_id) == (meta.session_id.bytes, meta.key_id.bytes)
    aead_key = derive_keys(_KEY, salt, (aead.name,))[aead.name]

    offset = _HEADER.size
    for index, plaintext in enumerate((b"ab", b"c")):
        counter = data[offset : offset + 8]
        assert counter == pack(">Q", index)
        end = offset + 8 + len(plaintext) + 16
        tagged = data[offset + 8 : end]
        nonce = prefix + counter
        final = index == 1
        aad = header + counter + pack(">QB", index, final)
        assert aead.decrypt(aead_key, nonce, tagged, aad) == plaintext
        with pytest.raises(InvalidTag):
            aead.decrypt(
                aead_key,
                nonce,
                tagged,
                header + counter + pack(">QB", index, not final),
            )
        with pytest.raises(InvalidTag):
            aead.decrypt(
                aead_key,
                nonce,
                tagged,
                header + counter + pack(">QB", index + 1, final),
            )
        offset = end
    assert offset == len(data)

    second = tmp_path / "second"
    encrypt_file(source, second, aead.name, _KEY, meta, chunk_size=2)
    other = second.read_bytes()
    assert _HEADER.unpack_from(other)[5] != salt
    sealed.write_bytes(header + other[_HEADER.size :])
    with pytest.raises(InvalidTag):
        decrypt_file(sealed, tmp_path / "opened", _lookup_fixture_key)
    assert not (tmp_path / "opened").exists()


@pytest.mark.parametrize(
    ("options", "error_type", "error"),
    [
        ({"chunk_size": 0}, ContainerError, "chunk size"),
        ({"chunk_size": MAX_CHUNK_SIZE + 1}, ContainerError, "chunk size"),
        ({"max_bytes_per_key": 0}, ValueError, "positive"),
        ({"max_bytes_per_key": 2}, ValueError, "byte limit"),
        ({"chunk_size": 1, "max_messages": 2}, NonceExhaustedError, "message limit"),
    ],
)
def test_encrypt_limit_rejections_are_atomic(
    tmp_path: Path, options: dict[str, int], error_type: type[Exception], error: str
) -> None:
    source, sealed = tmp_path / "source", tmp_path / "sealed"
    source.write_bytes(b"abc")
    sealed.write_bytes(b"previous output")
    with pytest.raises(error_type, match=error):
        encrypt_file(
            source, sealed, "aes256gcm", _KEY, SessionMeta(uuid4(), uuid4()), **options
        )
    assert sealed.read_bytes() == b"previous output"
    assert set(tmp_path.iterdir()) == {source, sealed}


def test_rejects_oversized_declarations_before_key_lookup(tmp_path: Path) -> None:
    source, sealed, opened = (
        tmp_path / name for name in ("source", "sealed", "opened")
    )
    source.write_bytes(b"")
    encrypt_file(source, sealed, "aes256gcm", _KEY, SessionMeta(uuid4(), uuid4()))
    data = sealed.read_bytes()

    def unexpected_lookup(_: bytes) -> bytes:
        pytest.fail("malformed container reached the key provider")

    for chunk_size, orig_size, error in (
        (MAX_CHUNK_SIZE + 1, 0, "chunk size"),
        (1, 2**32 + 1, "message limit"),
        (1, 63, "size does not match"),
    ):
        sealed.write_bytes(
            data[: _HEADER.size - 12]
            + pack(">IQ", chunk_size, orig_size)
            + data[_HEADER.size :]
        )
        with pytest.raises(ContainerError, match=error):
            decrypt_file(sealed, opened, unexpected_lookup)
    assert not opened.exists()


@pytest.mark.parametrize("aead", _CIPHERS)
def test_large_file_round_trip_uses_constant_memory(tmp_path: Path, aead: Aead) -> None:
    source, sealed, opened = (
        tmp_path / name for name in ("source", "sealed", "opened")
    )
    meta = SessionMeta(uuid4(), uuid4())
    block = b"\x01" * _MIB
    peaks = []
    for size_mib in (1, 32):
        with source.open("wb") as stream:
            for _ in range(size_mib):
                stream.write(block)

        tracemalloc.start()
        try:
            encrypt_file(source, sealed, aead.name, _KEY, meta)
            encrypt_peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.clear_traces()
            decrypt_file(sealed, opened, _lookup_fixture_key)
            decrypt_peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        with source.open("rb") as original, opened.open("rb") as recovered:
            assert (
                file_digest(original, "sha256").digest()
                == file_digest(recovered, "sha256").digest()
            )
        peaks.append((encrypt_peak, decrypt_peak))

    for small, large in zip(*peaks, strict=True):
        assert large < _MIB
        assert large < small + 256 * 1024
