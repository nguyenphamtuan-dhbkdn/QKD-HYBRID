"""Validated session configuration and YAML overrides."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeVar

import yaml

BasisMode = Literal["random", "fixed_z", "fixed_x"]
AttackKind = Literal["none", "ir", "pns"]
T = TypeVar("T")


def _integer(name: str, value: int, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _nonnegative(name: str, value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")


def _probability(name: str, value: float, *, open_interval: bool = False) -> None:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a probability")
    valid = 0 < value < 1 if open_interval else 0 <= value <= 1
    if not valid:
        interval = "(0, 1)" if open_interval else "[0, 1]"
        raise ValueError(f"{name} must be in {interval}")


def _choice(name: str, value: str, options: tuple[str, ...]) -> None:
    if value not in options:
        raise ValueError(f"{name} must be one of: {', '.join(options)}")


@dataclass(frozen=True)
class ChannelConfig:
    """Fibre attenuation, optical noise, and detector settings."""

    length_km: float = 0.0
    alpha_db_per_km: float = 0.2
    e_misalign: float = 0.01
    depol: float = 0.0
    bitflip: float = 0.0
    misalignment_theta: float | None = None
    eta_det: float = 1.0
    p_dark: float = 0.0

    def __post_init__(self) -> None:
        _nonnegative("channel.length_km", self.length_km)
        _nonnegative("channel.alpha_db_per_km", self.alpha_db_per_km)
        _probability("channel.e_misalign", self.e_misalign)
        _probability("channel.depol", self.depol)
        _probability("channel.bitflip", self.bitflip)
        if self.misalignment_theta is not None:
            _nonnegative("channel.misalignment_theta", self.misalignment_theta)
            if self.misalignment_theta > math.pi / 2:
                raise ValueError("channel.misalignment_theta must be in [0, pi/2]")
        _probability("channel.eta_det", self.eta_det)
        _probability("channel.p_dark", self.p_dark)


@dataclass(frozen=True)
class SourceConfig:
    """Select single photons or coherent pulses with mean photon count mu."""

    kind: Literal["single_photon", "weak_coherent"] = "single_photon"
    mu: float | None = None

    def __post_init__(self) -> None:
        _choice("source.kind", self.kind, ("single_photon", "weak_coherent"))
        if self.mu is not None:
            _nonnegative("source.mu", self.mu)
        elif self.kind == "weak_coherent":
            raise ValueError("source.mu is required for weak_coherent pulses")


@dataclass(frozen=True, init=False)
class AttackConfig:
    """Attack selection, intercept probability, and Eve's basis policy."""

    kind: AttackKind
    p: float
    basis_mode: BasisMode

    def __init__(
        self,
        kind: AttackKind = "none",
        p: float | None = None,
        basis_mode: BasisMode | Literal["fixed_Z", "fixed_X"] = "random",
    ) -> None:
        _choice("attack.kind", kind, ("none", "ir", "pns"))
        if p is None:
            p = 0.0 if kind == "none" else 1.0
        _probability("attack.p", p)
        if basis_mode == "fixed_Z":
            basis_mode = "fixed_z"
        elif basis_mode == "fixed_X":
            basis_mode = "fixed_x"
        _choice("attack.basis_mode", basis_mode, ("random", "fixed_z", "fixed_x"))
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "p", p)
        object.__setattr__(self, "basis_mode", basis_mode)


@dataclass(frozen=True)
class BB84Config:
    """Pulse generation and BB84 parameter estimation settings."""

    n_pulses: int = 200_000
    p_z: float = 0.5
    test_fraction: float = 0.1
    k_min: int = 200
    q_max: float = 0.11
    eps_pe: float = 1e-10
    eps_sec: float = 1e-9
    eps_cor: float = 1e-12
    ec_mode: Literal["cascade", "ideal"] = "cascade"
    f_ec_ideal: float = 1.0
    backend: Literal["fast", "qiskit"] = "fast"

    def __post_init__(self) -> None:
        _integer("bb84.n_pulses", self.n_pulses, 1)
        _integer("bb84.k_min", self.k_min, 1)
        _probability("bb84.p_z", self.p_z)
        _probability("bb84.test_fraction", self.test_fraction)
        if self.test_fraction == 0:
            raise ValueError("bb84.test_fraction must be positive")
        _probability("bb84.q_max", self.q_max)
        _probability("bb84.eps_pe", self.eps_pe, open_interval=True)
        _probability("bb84.eps_sec", self.eps_sec, open_interval=True)
        _probability("bb84.eps_cor", self.eps_cor, open_interval=True)
        _choice("bb84.ec_mode", self.ec_mode, ("cascade", "ideal"))
        _nonnegative("bb84.f_ec_ideal", self.f_ec_ideal)
        if self.f_ec_ideal < 1:
            raise ValueError("bb84.f_ec_ideal must be >= 1")
        _choice("bb84.backend", self.backend, ("fast", "qiskit"))


@dataclass(frozen=True)
class E91Config:
    """E91 settings reserved in the shared configuration schema."""

    n_pairs: int = 200_000
    visibility: float = 1.0
    chsh_z: float = 5.0

    def __post_init__(self) -> None:
        _integer("e91.n_pairs", self.n_pairs, 1)
        _probability("e91.visibility", self.visibility)
        _nonnegative("e91.chsh_z", self.chsh_z)


@dataclass(frozen=True)
class MonitorConfig:
    """Monitor settings reserved in the shared configuration schema."""

    detector: Literal["threshold", "ci", "sprt", "cusum", "joint"] = "sprt"
    alpha: float = 1e-3
    beta: float = 1e-3
    e0: float = 0.02
    e1: float = 0.10

    def __post_init__(self) -> None:
        modes = ("threshold", "ci", "sprt", "cusum", "joint")
        _choice("monitor.detector", self.detector, modes)
        _probability("monitor.alpha", self.alpha, open_interval=True)
        _probability("monitor.beta", self.beta, open_interval=True)
        _probability("monitor.e0", self.e0)
        _probability("monitor.e1", self.e1)
        if self.e0 >= self.e1:
            raise ValueError("monitor.e0 must be less than monitor.e1")


@dataclass(frozen=True)
class CryptoConfig:
    """Cipher settings reserved in the shared configuration schema."""

    cipher: Literal["aes256gcm", "chacha20poly1305", "otp"] = "aes256gcm"
    chunk_size: int = 65_536
    max_bytes_per_key: int = 1_073_741_824

    def __post_init__(self) -> None:
        _choice("crypto.cipher", self.cipher, ("aes256gcm", "chacha20poly1305", "otp"))
        _integer("crypto.chunk_size", self.chunk_size, 1)
        _integer("crypto.max_bytes_per_key", self.max_bytes_per_key, 1)


@dataclass(frozen=True)
class SessionConfig:
    """Top-level settings and the seed for all draws in a session."""

    seed: int = 20_260_116
    bb84: BB84Config = field(default_factory=BB84Config)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    attack: AttackConfig = field(default_factory=AttackConfig)
    e91: E91Config = field(default_factory=E91Config)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    source: SourceConfig = field(default_factory=SourceConfig)

    def __post_init__(self) -> None:
        _integer("seed", self.seed, 0)


def _load_section(name: str, raw: object, config_type: type[T]) -> T:
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be a mapping")
    try:
        return config_type(**raw)
    except TypeError as exc:
        raise ValueError(f"Invalid {name} configuration: {exc}") from exc


def load_config(path: Path | None = None) -> SessionConfig:
    """Read safe YAML overrides, or construct defaults when path is omitted."""
    if path is None:
        return SessionConfig()
    try:
        with path.open(encoding="utf-8-sig") as config_file:
            raw = yaml.safe_load(config_file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a mapping")
    sections = {
        "seed",
        "bb84",
        "channel",
        "attack",
        "e91",
        "monitor",
        "crypto",
        "source",
    }
    if unknown := raw.keys() - sections:
        names = ", ".join(sorted(map(str, unknown)))
        raise ValueError(f"Unknown configuration sections: {names}")
    return SessionConfig(
        seed=raw.get("seed", SessionConfig.seed),
        bb84=_load_section("bb84", raw.get("bb84", {}), BB84Config),
        channel=_load_section("channel", raw.get("channel", {}), ChannelConfig),
        attack=_load_section("attack", raw.get("attack", {}), AttackConfig),
        e91=_load_section("e91", raw.get("e91", {}), E91Config),
        monitor=_load_section("monitor", raw.get("monitor", {}), MonitorConfig),
        crypto=_load_section("crypto", raw.get("crypto", {}), CryptoConfig),
        source=_load_section("source", raw.get("source", {}), SourceConfig),
    )
