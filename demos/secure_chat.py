"""Trình diễn BB84 và AEAD giữa Alice và Bob qua TCP cục bộ."""

import argparse
import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from struct import Struct

from qkdsim._terminal import configure_utf8
from qkdsim.auth.channel import Party
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import AttackConfig, SessionConfig, load_config
from qkdsim.crypto.aead import Aead, AesGcm256, ChaCha20Poly1305, NonceSequence
from qkdsim.crypto.kdf import derive_keys
from qkdsim.monitor.policy import SessionUnavailable
from qkdsim.monitor.session import MonitoredSession
from qkdsim.postprocess.result import AbortEvidence
from qkdsim.rng import SimRNG, secure_random
from qkdsim.simulation import run_bb84_link

SIZE = Struct("!I")
SEQUENCE = Struct("!Q")
MAX_FRAME = 16 * 1024**2
MAX_MESSAGE = 65_536
FRAME_TIMEOUT = 15.0
CIPHERS: dict[str, Aead] = {"aes256gcm": AesGcm256(), "chacha20": ChaCha20Poly1305()}


@dataclass
class Endpoint:
    """The read and write streams on one side of a loopback TCP connection."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter


@dataclass
class Wire:
    """Carry each authenticated classical or encrypted application frame over TCP."""

    alice: Endpoint
    bob: Endpoint

    async def exchange(self, sender: Party, frame: bytes) -> bytes:
        """Write length || frame from the sender and read it at the receiver."""
        source, target = (
            (self.alice, self.bob) if sender == "alice" else (self.bob, self.alice)
        )
        if len(frame) > MAX_FRAME:
            raise ValueError("Khung vượt giới hạn TCP của bản trình diễn.")

        async def receive() -> bytes:
            (size,) = SIZE.unpack(await target.reader.readexactly(SIZE.size))
            if size > MAX_FRAME:
                raise ValueError("Độ dài khung nhận được vượt giới hạn.")
            return await target.reader.readexactly(size)

        source.writer.write(SIZE.pack(len(frame)) + frame)
        _, received = await asyncio.wait_for(
            asyncio.gather(source.writer.drain(), receive()), timeout=FRAME_TIMEOUT
        )
        return received


@asynccontextmanager
async def loopback() -> AsyncIterator[Wire]:
    """Accept a single loopback TCP connection with independently owned streams."""
    accepted: asyncio.Future[Endpoint] = asyncio.get_running_loop().create_future()

    def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not accepted.done():
            accepted.set_result(Endpoint(reader, writer))
        else:
            writer.close()

    async with await asyncio.start_server(accept, "127.0.0.1", 0) as server:
        port = int(server.sockets[0].getsockname()[1])
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), timeout=5
        )
        bob = await asyncio.wait_for(accepted, timeout=5)
    try:
        yield Wire(Endpoint(reader, writer), bob)
    finally:
        writer.close()
        bob.writer.close()
        await asyncio.gather(writer.wait_closed(), bob.writer.wait_closed())


@dataclass(repr=False)
class ChatKeys:
    """Separate endpoint keys, one unique nonce stream and an ordered transcript."""

    alice: bytes
    bob: bytes
    aad_prefix: bytes
    nonces: NonceSequence
    sequence: int = 0

    async def send(self, wire: Wire, cipher: Aead, payload: bytes) -> bytes:
        """Bind version, cipher, session, key ID and expected counter to the AEAD."""
        aad = self.aad_prefix + SEQUENCE.pack(self.sequence)
        nonce = self.nonces.next_nonce()
        packet = await wire.exchange(
            "alice", nonce + cipher.encrypt(self.alice, nonce, payload, aad)
        )
        opened = cipher.decrypt(
            self.bob, packet[: cipher.nonce_size], packet[cipher.nonce_size :], aad
        )
        self.sequence += 1
        return opened


class Chat:
    """Acquire monitored BB84 keys, authorize usage, and block on any abort."""

    def __init__(
        self,
        config: SessionConfig,
        cipher: Aead,
        output: Path,
        wire: Wire,
    ) -> None:
        self.config = config
        self.cipher = cipher
        self.output = output
        self.wire = wire
        self.rng = SimRNG(config.seed).generator
        self.auth = AuthenticationPool()
        self.keys: ChatKeys | None = None
        self.session: MonitoredSession | None = None
        self.eve = False

    def toggle_eve(self, enabled: bool) -> None:
        """Retire the active key when the simulated optical route changes."""
        if self.eve != enabled:
            self.eve = enabled
            self.keys = None
        print("Eve bật." if enabled else "Eve tắt.")

    async def rekey(self) -> bool:
        """Run the synchronous BB84 state machine with its HMAC traffic on TCP."""
        if self.session is not None:
            policy = self.session.policy
            await asyncio.sleep(max(0, policy.retry_at - self.session.clock()))
        else:
            policy = None
        cfg = replace(
            self.config, attack=AttackConfig("ir") if self.eve else AttackConfig()
        )
        session = MonitoredSession(cfg, output=self.output)
        if policy is not None:
            session.policy = policy
        self.session = session
        loop = asyncio.get_running_loop()

        def transport(sender: Party, _kind: str, frame: bytes) -> bytes:
            pending = asyncio.run_coroutine_threadsafe(
                self.wire.exchange(sender, frame), loop
            )
            return pending.result()

        try:
            link = await asyncio.to_thread(
                run_bb84_link,
                cfg,
                self.rng,
                session=session,
                authentication=self.auth,
                transport=transport,
            )
        except SessionUnavailable as exc:
            print(f"Từ chối gửi: {exc}.")
            return False
        if isinstance(link, AbortEvidence):
            assert session.directory is not None
            evidence = session.directory / "evidence.json"
            print(
                json.dumps(
                    {
                        "status": "ABORT",
                        "reason": link.reason,
                        "qber": session.metrics.qber,
                        "evidence": str(evidence),
                    },
                    ensure_ascii=False,
                )
            )
            print(f"Biểu đồ QBER: {session.directory / 'qber.png'}")
            return False
        key = link.alice
        if key.length_bits < 256:
            print("Từ chối gửi: khóa còn dưới 256 bit.")
            return False
        salt = await self.wire.exchange("alice", secure_random(16))
        label = self.cipher.name
        self.keys = ChatKeys(
            derive_keys(key.key_bytes, salt, (label,))[label],
            derive_keys(link.bob_bytes, salt, (label,))[label],
            b"QKDH-chat-v1"
            + label.encode("ascii")
            + key.session_id.bytes
            + key.key_id.bytes,
            NonceSequence(max_messages=cfg.monitor.max_msgs),
        )
        print(
            json.dumps(
                {
                    "status": "KEY_READY",
                    "session_id": str(key.session_id),
                    "key_bits": key.length_bits,
                    "qber": key.qber,
                }
            )
        )
        return True

    async def send(self, text: str) -> str | None:
        """Deliver a message only after a current key passes monitor authorization."""
        payload = text.encode("utf-8")
        if len(payload) > min(MAX_MESSAGE, self.config.crypto.max_bytes_per_key):
            raise ValueError("Tin nhắn quá dài.")
        if self.keys is not None:
            assert self.session is not None
            try:
                self.session.authorize_message(len(payload))
            except SessionUnavailable:
                self.keys = None
            else:
                return (await self.keys.send(self.wire, self.cipher, payload)).decode(
                    "utf-8"
                )
        if not await self.rekey():
            return None
        assert self.session is not None and self.keys is not None
        try:
            self.session.authorize_message(len(payload))
        except SessionUnavailable as exc:
            self.keys = None
            print(f"Từ chối gửi: {exc}.")
            return None
        return (await self.keys.send(self.wire, self.cipher, payload)).decode("utf-8")


async def self_test(chat: Chat) -> None:
    """Check a clean delivery, rekey limit, blocked delivery and recovery."""
    assert await chat.send("Xin chào Bob") == "Xin chào Bob"
    assert chat.session is not None
    first = chat.session.session_id
    assert await chat.send("Đổi khóa") == "Đổi khóa"
    assert chat.session.session_id != first
    chat.toggle_eve(True)
    assert await chat.send("Tin nhắn bị chặn") is None and chat.keys is None
    assert chat.session.directory is not None
    assert (chat.session.directory / "evidence.json").is_file()
    chat.toggle_eve(False)
    assert await chat.send("Khôi phục sau khi tắt Eve") == "Khôi phục sau khi tắt Eve"
    print("D1 đạt kiểm tra gửi, đổi khóa, dừng và khôi phục.")


async def run(args: argparse.Namespace) -> None:
    """Run a scripted check or a single-terminal interactive chat."""
    cfg = load_config(args.config)
    cfg = replace(
        cfg,
        monitor=replace(
            cfg.monitor, max_msgs=1 if args.self_test else args.rekey_every
        ),
    )
    async with loopback() as wire:
        chat = Chat(cfg, CIPHERS[args.cipher], args.output, wire)
        if args.self_test:
            await self_test(chat)
            return
        chat.toggle_eve(args.eve)
        print("/eve on · /eve off · /reset · /quit")
        while True:
            try:
                text = await asyncio.to_thread(input, "Alice> ")
            except EOFError:
                return
            if text == "/quit":
                return
            if text in ("/eve on", "/eve off"):
                chat.toggle_eve(text.endswith("on"))
            elif text == "/reset":
                if chat.session is not None:
                    chat.session.policy.reset()
                chat.keys = None
            elif text:
                try:
                    opened = await chat.send(text)
                except ValueError as exc:
                    print(exc)
                else:
                    if opened is not None:
                        print(f"Bob> {opened}")


def main() -> None:
    """Accept demo-only settings and open a local TCP connection."""
    configure_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/demo_chat"))
    parser.add_argument("--cipher", choices=CIPHERS, default="aes256gcm")
    parser.add_argument("--rekey-every", type=int, default=3)
    parser.add_argument("--eve", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not 0 < args.rekey_every <= (1 << 20):
        parser.error("--rekey-every phải nằm trong [1, 2**20]")
    try:
        asyncio.run(run(args))
    except (OSError, asyncio.IncompleteReadError) as exc:
        parser.exit(1, f"Lỗi kết nối TCP cục bộ: {exc or type(exc).__name__}\n")


if __name__ == "__main__":
    main()
