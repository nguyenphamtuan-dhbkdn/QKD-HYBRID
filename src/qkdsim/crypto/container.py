"""QKDH v1 file encryption with authenticated framing and streaming I/O."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from os import fstat
from pathlib import Path
from secrets import token_bytes
from struct import Struct
from tempfile import NamedTemporaryFile
from typing import IO, BinaryIO
from uuid import UUID

from qkdsim.config import CryptoConfig
from qkdsim.crypto.aead import (
    COUNTER_SIZE,
    DEFAULT_MAX_MESSAGES,
    MAX_MESSAGES,
    NONCE_PREFIX_SIZE,
    TAG_SIZE,
    Aead,
    AesGcm256,
    ChaCha20Poly1305,
    NonceExhaustedError,
    NonceSequence,
)
from qkdsim.crypto.kdf import derive_keys

_MAGIC = b"QKDH"
_VERSION = 1
_SALT_SIZE = 16
_HEADER = Struct(f">4sBB16s16s{_SALT_SIZE}s{NONCE_PREFIX_SIZE}sIQ")
_CHUNK_CONTEXT = Struct(">Q?")
_CHUNK_OVERHEAD = COUNTER_SIZE + TAG_SIZE
_CIPHERS: dict[int, Aead] = {1: AesGcm256(), 2: ChaCha20Poly1305()}
_CIPHER_IDS = {cipher.name: cipher_id for cipher_id, cipher in _CIPHERS.items()}
_DEFAULTS = CryptoConfig()
MAX_CHUNK_SIZE = 16 * 1024**2


class ContainerError(ValueError):
    """Invalid or unsupported QKDH framing."""


@dataclass(frozen=True)
class SessionMeta:
    """Public identifiers from the key exchange that yielded the input key."""

    session_id: UUID
    key_id: UUID


@dataclass(frozen=True)
class _FileReport:
    cipher: str
    session_meta: SessionMeta
    plaintext_bytes: int
    container_bytes: int
    chunks: int


@dataclass(frozen=True)
class EncryptionReport(_FileReport):
    """Public metadata and byte counts for a completed encryption."""


@dataclass(frozen=True)
class DecryptionReport(_FileReport):
    """Authenticated metadata and byte counts for a completed decryption."""


@dataclass(frozen=True)
class _Header:
    cipher_id: int
    session_meta: SessionMeta
    salt: bytes
    nonce_prefix: bytes
    chunk_size: int
    orig_size: int

    def encode(self) -> bytes:
        return _HEADER.pack(
            _MAGIC,
            _VERSION,
            self.cipher_id,
            self.session_meta.session_id.bytes,
            self.session_meta.key_id.bytes,
            self.salt,
            self.nonce_prefix,
            self.chunk_size,
            self.orig_size,
        )

    @classmethod
    def decode(cls, data: bytes) -> "_Header":
        magic, version, cipher_id, session, key, salt, prefix, chunk, size = (
            _HEADER.unpack(data)
        )
        if magic != _MAGIC or version != _VERSION:
            raise ContainerError("unsupported QKDH magic or version")
        if cipher_id not in _CIPHERS:
            raise ContainerError("unsupported cipher ID")
        _check_chunk_size(chunk)
        return cls(
            cipher_id,
            SessionMeta(UUID(bytes=session), UUID(bytes=key)),
            salt,
            prefix,
            chunk,
            size,
        )

    @property
    def chunks(self) -> int:
        """Return max(1, ceil(original size / chunk size))."""
        return max(1, (self.orig_size + self.chunk_size - 1) // self.chunk_size)

    def plaintext_size(self, index: int) -> int:
        return min(self.chunk_size, self.orig_size - index * self.chunk_size)

    def wire_size(self, chunks: int) -> int:
        """Return header bytes + original bytes + chunks * (counter + tag bytes)."""
        return _HEADER.size + self.orig_size + chunks * _CHUNK_OVERHEAD


def _check_chunk_size(chunk_size: int) -> None:
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ContainerError(f"chunk size must be in [1, {MAX_CHUNK_SIZE}]")


def _aad(header: bytes, counter: bytes, chunk_index: int, final_chunk: bool) -> bytes:
    """Bind the exact wire header, sequence counter, chunk index, and final flag."""
    return header + counter + _CHUNK_CONTEXT.pack(chunk_index, final_chunk)


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ContainerError("unexpected end of file")
    return data


def _require_eof(stream: BinaryIO) -> None:
    if stream.read(1):
        raise ContainerError("unexpected trailing data")


@contextmanager
def _atomic_output(destination: Path) -> Iterator[IO[bytes]]:
    """Stage output beside the destination, then replace after closing the file."""
    temporary = NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False)
    staged = Path(temporary.name)
    try:
        with temporary:
            yield temporary
        staged.replace(destination)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def encrypt_file(
    path_in: Path,
    path_out: Path,
    cipher: str,
    key: bytes,
    session_meta: SessionMeta,
    *,
    chunk_size: int = _DEFAULTS.chunk_size,
    max_bytes_per_key: int = _DEFAULTS.max_bytes_per_key,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> EncryptionReport:
    """Derive a fresh AEAD key from QKD bytes and seal one record per chunk.

    Each chunk uses one nonce. Empty input has one authenticated empty record.
    """
    if cipher not in _CIPHER_IDS:
        raise ValueError("unsupported container cipher")
    _check_chunk_size(chunk_size)
    if type(max_bytes_per_key) is not int or max_bytes_per_key < 1:
        raise ValueError("per-key byte limit must be positive")

    cipher_id = _CIPHER_IDS[cipher]
    aead = _CIPHERS[cipher_id]
    nonces = NonceSequence(max_messages)
    salt = token_bytes(_SALT_SIZE)
    aead_key = derive_keys(key, salt, (cipher,))[cipher]
    with _atomic_output(path_out) as output, path_in.open("rb") as source:
        orig_size = fstat(source.fileno()).st_size
        if orig_size > max_bytes_per_key:
            raise ValueError("per-key byte limit exceeded")
        header = _Header(
            cipher_id, session_meta, salt, nonces.prefix, chunk_size, orig_size
        )
        chunks = header.chunks
        if chunks > max_messages:
            raise NonceExhaustedError("per-key message limit exceeded")
        wire_header = header.encode()
        output.write(wire_header)
        for index in range(chunks):
            plaintext = _read_exact(source, header.plaintext_size(index))
            nonce = nonces.next_nonce()
            counter = nonce[NONCE_PREFIX_SIZE:]
            aad = _aad(wire_header, counter, index, index == chunks - 1)
            output.write(counter)
            output.write(aead.encrypt(aead_key, nonce, plaintext, aad))
        _require_eof(source)
    return EncryptionReport(
        cipher, session_meta, orig_size, header.wire_size(chunks), chunks
    )


def decrypt_file(
    path_in: Path,
    path_out: Path,
    key_provider: Callable[[bytes], bytes],
) -> DecryptionReport:
    """Resolve raw QKD bytes by public key ID and verify all records before commit.

    The key ID passed to the provider comes from the unauthenticated header.
    """
    with _atomic_output(path_out) as output, path_in.open("rb") as source:
        wire_header = _read_exact(source, _HEADER.size)
        header = _Header.decode(wire_header)
        chunks = header.chunks
        wire_size = header.wire_size(chunks)
        if chunks > MAX_MESSAGES:
            raise ContainerError("container exceeds the hard per-key message limit")
        if fstat(source.fileno()).st_size != wire_size:
            raise ContainerError("file size does not match the QKDH header")

        aead = _CIPHERS[header.cipher_id]
        key = key_provider(header.session_meta.key_id.bytes)
        aead_key = derive_keys(key, header.salt, (aead.name,))[aead.name]
        for index in range(chunks):
            counter = _read_exact(source, COUNTER_SIZE)
            if int.from_bytes(counter, "big") != index:
                raise ContainerError("unexpected chunk counter")
            sealed = _read_exact(source, header.plaintext_size(index) + TAG_SIZE)
            nonce = header.nonce_prefix + counter
            aad = _aad(wire_header, counter, index, index == chunks - 1)
            output.write(aead.decrypt(aead_key, nonce, sealed, aad))
        _require_eof(source)
    return DecryptionReport(
        aead.name, header.session_meta, header.orig_size, wire_size, chunks
    )
