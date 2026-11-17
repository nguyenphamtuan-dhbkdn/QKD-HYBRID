"""Demo-only QKD key storage and QKDH file commands."""

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from cryptography.exceptions import InvalidTag

from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import load_config
from qkdsim.crypto.container import SessionMeta, decrypt_file, encrypt_file
from qkdsim.postprocess.result import AbortEvidence, FinalKey
from qkdsim.simulation import run_bb84_link


class DemoCipher(StrEnum):
    """Cipher names accepted by the file demo."""

    AES = "aes256gcm"
    CHACHA = "chacha20"

    @property
    def container_name(self) -> str:
        """Map the CLI alias to the library cipher identifier."""
        return "chacha20poly1305" if self is DemoCipher.CHACHA else self.value


def _describe(key: FinalKey) -> dict[str, str | int | float]:
    """Return public key provenance for terminal output."""
    return {
        "key_id": str(key.key_id),
        "session_id": str(key.session_id),
        "qber": key.qber,
        "key_bits": key.length_bits,
    }


def _make_sidecar(path: Path, key: FinalKey, bob_bytes: bytes) -> None:
    """Create an exclusive demo-only key file with owner-only POSIX permissions."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({**_describe(key), "key_hex": bob_bytes.hex()}, stream)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _sidecar(path: Path, source: Path, destination: Path) -> Path:
    """Fail early if any input, output, or sidecar path aliases another path."""
    if len({path.resolve(), source.resolve(), destination.resolve()}) != 3:
        raise ValueError("Tệp vào, tệp ra và tệp khóa phải có đường dẫn riêng.")
    return path


def encrypt(
    path_in: Annotated[Path, typer.Option("--in", exists=True, dir_okay=False)],
    path_out: Annotated[Path, typer.Option("--out", dir_okay=False)],
    cipher: Annotated[DemoCipher, typer.Option()] = DemoCipher.AES,
    key_file: Annotated[Path | None, typer.Option(dir_okay=False)] = None,
    config: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Mô phỏng BB84, mã hóa QKDH và lưu khóa demo cục bộ."""
    try:
        sidecar = _sidecar(
            key_file or path_out.with_suffix(path_out.suffix + ".demo-key.json"),
            path_in,
            path_out,
        )
        cfg = load_config(config)
        link = run_bb84_link(cfg, authentication=AuthenticationPool())
        if isinstance(link, AbortEvidence):
            raise ValueError(f"Phiên {link.session_id} đã dừng ({link.reason}).")
        key = link.alice
        if key.length_bits < 256:
            raise ValueError(
                "Khóa QKD sau khi dành bit xác thực phải có ít nhất 256 bit."
            )
        _make_sidecar(sidecar, key, link.bob_bytes)
        try:
            report = encrypt_file(
                path_in,
                path_out,
                cipher.container_name,
                key.key_bytes,
                SessionMeta(key.session_id, key.key_id),
                chunk_size=cfg.crypto.chunk_size,
                max_bytes_per_key=cfg.crypto.max_bytes_per_key,
            )
        except BaseException:
            sidecar.unlink(missing_ok=True)
            raise
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"Mã hóa thất bại. {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                **_describe(key),
                "cipher": report.cipher,
                "plaintext_bytes": report.plaintext_bytes,
                "demo_key_file": str(sidecar),
            },
            ensure_ascii=False,
        )
    )


def decrypt(
    path_in: Annotated[Path, typer.Option("--in", exists=True, dir_okay=False)],
    path_out: Annotated[Path, typer.Option("--out", dir_okay=False)],
    key_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Kiểm tra thẻ AEAD rồi khôi phục tệp bằng khóa demo cục bộ."""
    try:
        sidecar = _sidecar(
            key_file or path_in.with_suffix(path_in.suffix + ".demo-key.json"),
            path_in,
            path_out,
        )
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        key_id = UUID(record["key_id"])
        qber, bits = float(record["qber"]), int(record["key_bits"])
        material = bytes.fromhex(record["key_hex"])
        if not 0 <= qber <= 1 or bits < 256 or (bits + 7) // 8 != len(material):
            raise ValueError("Thông tin khóa demo sai định dạng.")

        def resolve(received_id: bytes) -> bytes:
            if received_id != key_id.bytes:
                raise ValueError("Mã khóa trong tệp QKDH khác mã khóa demo.")
            return material

        report = decrypt_file(path_in, path_out, resolve)
    except InvalidTag as exc:
        typer.echo("Giải mã thất bại. Thẻ AEAD không hợp lệ.", err=True)
        raise typer.Exit(1) from exc
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # The opened key record may contain private material in malformed fields.
        typer.echo("Giải mã thất bại. Kiểm tra tệp QKDH và tệp khóa demo.", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "session_id": str(report.session_meta.session_id),
                "key_id": str(key_id),
                "qber": qber,
                "key_bits": bits,
                "cipher": report.cipher,
                "plaintext_bytes": report.plaintext_bytes,
            },
            ensure_ascii=False,
        )
    )
