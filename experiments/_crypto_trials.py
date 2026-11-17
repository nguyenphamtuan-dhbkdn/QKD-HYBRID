"""E9–E12: benchmark, file round trips, tamper tests, and classical MITM."""

import hashlib
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import numpy as np
from _protocols import settings
from _provenance import ROOT
from _suite import Experiment
from cryptography.exceptions import InvalidTag

from qkdsim.attacks.mitm_classical import run_classical_mitm
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import load_config
from qkdsim.crypto.aead import (
    COUNTER_SIZE,
    TAG_SIZE,
    AesGcm256,
    ChaCha20Poly1305,
    NonceSequence,
)
from qkdsim.crypto.container import (
    ContainerError,
    SessionMeta,
    decrypt_file,
    encrypt_file,
)
from qkdsim.postprocess.result import AbortEvidence
from qkdsim.rng import secure_random
from qkdsim.simulation import run_bb84_link

CIPHERS = (AesGcm256(), ChaCha20Poly1305())


def _chunk(kind: bytes, data: bytes) -> bytes:
    """Serialize a PNG chunk with a CRC-32 over its type and payload."""
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def fixture(path: Path, kind: str, size: int) -> None:
    """Generate text, valid PNG with ancillary padding, or random bytes."""
    block = 1024**2
    text = (b"QKD-HYBRID benchmark data.\n" * block)[:block] if kind == "text" else b""
    with path.open("wb") as output:
        if kind == "PNG":
            header = b"\x89PNG\r\n\x1a\n" + _chunk(
                b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            )
            header += _chunk(b"IDAT", zlib.compress(b"\x00\x13\x77\xcc"))
            end = _chunk(b"IEND", b"")
            output.write(header)
            size -= len(header) + len(end)
            while size >= 12:
                count = min(size, block)
                if 0 < size - count < 12:
                    count -= 12
                output.write(_chunk(b"paDd", bytes(count - 12)))
                size -= count
            if size:
                raise ValueError("invalid fixture PNG size")
            output.write(end)
            return
        for start in range(0, size, block):
            count = min(size - start, block)
            output.write(text[:count] if text else secure_random(count))


def e09(exp: Experiment) -> None:
    """Time streaming QKDH encrypt/decrypt after separate per-case warm-ups."""
    cap = exp.options["cap_bytes"]
    if exp.quick:
        cap = min(cap, exp.options["quick_cap_bytes"])
    with TemporaryDirectory() as tmp:
        source, encrypted, restored = (
            Path(tmp) / name for name in ("in", "enc", "out")
        )
        key, meta = secure_random(32), SessionMeta(uuid4(), uuid4())
        for size in exp.options["sizes"]:
            if size > cap:
                continue
            for kind in ("text", "PNG", "random"):
                fixture(source, kind, size)
                for cipher in CIPHERS:
                    enc, dec = [], []
                    for trial in range(exp.repeats + 1):
                        start = perf_counter()
                        encrypt_file(source, encrypted, cipher.name, key, meta)
                        mid = perf_counter()
                        decrypt_file(encrypted, restored, lambda _: key)
                        end = perf_counter()
                        if trial:
                            enc.append(mid - start)
                            dec.append(end - mid)
                    for action, samples in (("encrypt", enc), ("decrypt", dec)):
                        series = f"{cipher.name} · {kind}"
                        for metric, values in (
                            (f"{action}_mbps", [size / t / 1e6 for t in samples]),
                            (f"{action}_ms", [t * 1000 for t in samples]),
                        ):
                            low, mid, high = np.quantile(values, [0.25, 0.5, 0.75])
                            exp.point(
                                metric,
                                series,
                                size,
                                float(mid),
                                low=float(low),
                                high=float(high),
                                n=len(samples),
                                interval="IQR",
                            )


def _decrypt_fixture(source: Path, output: Path, material: bytes) -> None:
    """Open a synthetic fixture whose single key is already in scope."""
    decrypt_file(source, output, lambda _: material)


def digest(path: Path) -> str:
    """Return the SHA-256 of a file without buffering it in memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def e10(exp: Experiment) -> None:
    """Run authenticated QKD and verify each decrypted artifact by SHA-256."""
    cfg = settings(exp.options["pulses"], ideal_ec=True)
    with TemporaryDirectory() as tmp:
        for kind, size in (
            ("text", 1024),
            ("PNG", 4096),
            ("random", exp.options["file_bytes"]),
        ):
            source = Path(tmp) / "input"
            fixture(source, kind, size)
            expected = digest(source)
            for cipher in CIPHERS:
                stages: dict[str, list[float]] = {
                    name: [] for name in ("QKD", "encrypt", "decrypt", "hash")
                }
                successes = 0
                for i in range(exp.repeats):
                    start = perf_counter()
                    link = run_bb84_link(
                        cfg, exp.rng(i), authentication=AuthenticationPool()
                    )
                    qkd_end = perf_counter()
                    stages["QKD"].append(qkd_end - start)
                    if isinstance(link, AbortEvidence):
                        continue
                    encrypted, restored = (
                        Path(tmp) / "container",
                        Path(tmp) / "restored",
                    )
                    meta = SessionMeta(link.alice.session_id, link.alice.key_id)
                    encrypt_file(
                        source, encrypted, cipher.name, link.alice.key_bytes, meta
                    )
                    enc_end = perf_counter()
                    _decrypt_fixture(encrypted, restored, link.bob_bytes)
                    dec_end = perf_counter()
                    successes += digest(restored) == expected
                    end = perf_counter()
                    stages["encrypt"].append(enc_end - qkd_end)
                    stages["decrypt"].append(dec_end - enc_end)
                    stages["hash"].append(end - dec_end)
                series = f"{cipher.name} · {kind}"
                exp.proportion(
                    "integrity", cipher.name, kind, successes, exp.repeats, bytes=size
                )
                for stage, values in stages.items():
                    exp.mean(
                        "stage_ms",
                        series,
                        stage,
                        [t * 1000 for t in values],
                        bytes=size,
                    )


def _flip(data: bytes, offset: int) -> bytes:
    """Toggle exactly one bit in the selected wire byte."""
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1 :]


def e11(exp: Experiment) -> None:
    """Check tamper rejection and deliberate nonce reuse on disposable data."""
    plain_a, plain_b = b"message A", b"message B"
    expected_xor = bytes(x ^ y for x, y in zip(plain_a, plain_b, strict=True))
    chunk_size = 64
    chunk_overhead = COUNTER_SIZE + TAG_SIZE
    with TemporaryDirectory() as tmp:
        src, enc, out = (Path(tmp) / name for name in ("in", "enc", "out"))
        src.write_bytes(bytes(2 * chunk_size))
        for cipher in CIPHERS:
            counts = dict.fromkeys(
                ("header", "ciphertext", "tag", "truncate", "reorder"), 0
            )
            leaks = 0
            for _ in range(exp.repeats):
                key, meta = secure_random(32), SessionMeta(uuid4(), uuid4())
                report = encrypt_file(
                    src, enc, cipher.name, key, meta, chunk_size=chunk_size
                )
                block = chunk_size + chunk_overhead
                data = enc.read_bytes()
                header = report.container_bytes - 2 * block
                corruptions = (
                    _flip(data, header - 13),
                    _flip(data, header + COUNTER_SIZE),
                    _flip(data, header + block - 1),
                    data[:-1],
                    data[:header]
                    + data[header + block :]
                    + data[header : header + block],
                )
                for kind, damaged in zip(counts, corruptions, strict=True):
                    enc.write_bytes(damaged)
                    try:
                        _decrypt_fixture(enc, out, key)
                    except (ContainerError, InvalidTag):
                        counts[kind] += 1
                    else:
                        out.unlink()
                misuse_key = secure_random(32)
                nonce = NonceSequence().next_nonce()
                a = cipher.encrypt(misuse_key, nonce, plain_a, b"")[: len(plain_a)]
                b = cipher.encrypt(misuse_key, nonce, plain_b, b"")[: len(plain_b)]
                leaks += bytes(x ^ y for x, y in zip(a, b, strict=True)) == expected_xor
            for kind, count in counts.items():
                exp.proportion("tamper", cipher.name, kind, count, exp.repeats)
            exp.proportion("nonce_leak", cipher.name, "nonce reuse", leaks, exp.repeats)


def e12(exp: Experiment) -> None:
    """Count real Eve key agreements and authentication-tag rejections."""
    cfg = load_config(ROOT / "configs" / exp.options["session"])
    for auth in (False, True):
        outcomes = [
            run_classical_mitm(cfg, exp.rng(i), authenticated=auth)
            for i in range(exp.repeats)
        ]
        rejected = sum(
            o.alice_abort == o.bob_abort == "authentication tag mismatch"
            for o in outcomes
        )
        exp.proportion(
            "mitm",
            "BB84",
            "HMAC" if auth else "no HMAC",
            sum(o.succeeded for o in outcomes),
            exp.repeats,
            both_tags_rejected=rejected,
        )
