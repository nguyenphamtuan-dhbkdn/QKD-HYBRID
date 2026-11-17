"""Chạy lệnh mã hóa/giải mã demo hoặc kiểm tra khứ hồi hai AEAD."""

from pathlib import Path
from tempfile import TemporaryDirectory

import typer

from qkdsim._terminal import configure_utf8
from qkdsim.file_demo import DemoCipher, decrypt, encrypt

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.command()(encrypt)
app.command()(decrypt)


@app.command()
def self_test() -> None:
    """Tạo tệp tổng hợp, mã hóa, giải mã và so sánh với bản gốc."""
    with TemporaryDirectory() as tmp:
        source, encrypted, restored = (
            Path(tmp) / name
            for name in (
                "message.txt",
                "message.qkdh",
                "message-restored.txt",
            )
        )
        source.write_text("Ví dụ mã hóa tệp QKDH.\n", encoding="utf-8")
        for cipher in DemoCipher:
            key_file = Path(tmp) / (cipher.value + ".demo-key.json")
            encrypt(source, encrypted, cipher, key_file)
            decrypt(encrypted, restored, key_file)
            if source.read_bytes() != restored.read_bytes():
                raise RuntimeError("Tệp giải mã khác tệp ban đầu.")
    typer.echo("D2 khôi phục đúng tệp với cả hai AEAD.")


if __name__ == "__main__":
    configure_utf8()
    app()
