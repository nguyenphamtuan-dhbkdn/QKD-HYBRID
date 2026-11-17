"""Round-trip the public file CLI and verify a tamper cannot publish plaintext."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qkdsim.cli import app

runner = CliRunner()


@pytest.mark.parametrize("cipher", ["aes256gcm", "chacha20"])
def test_file_cli_round_trip(cipher: str, tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    container = tmp_path / "sealed.qkdh"
    restored = tmp_path / "restored.txt"
    source.write_text("Trình diễn QKD\n", encoding="utf-8")
    encrypt = runner.invoke(
        app,
        ["encrypt", "--in", str(source), "--out", str(container), "--cipher", cipher],
    )
    assert encrypt.exit_code == 0, encrypt.output
    sent = json.loads(encrypt.output)
    with Path(sent["demo_key_file"]).open(encoding="utf-8") as stream:
        sidecar = json.load(stream)
    assert sidecar["key_hex"] not in encrypt.output
    decrypt_args = ["decrypt", "--in", str(container), "--out", str(restored)]
    decrypt = runner.invoke(app, decrypt_args)
    assert decrypt.exit_code == 0, decrypt.output
    received = json.loads(decrypt.output)
    assert received["session_id"] == sent["session_id"]
    assert received["key_id"] == sent["key_id"]
    assert received["key_bits"] >= 256
    assert sidecar["key_hex"] not in decrypt.output
    assert source.read_bytes() == restored.read_bytes()

    original = container.read_bytes()
    container.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    tampered = runner.invoke(app, decrypt_args)
    assert tampered.exit_code != 0
    assert source.read_bytes() == restored.read_bytes()
