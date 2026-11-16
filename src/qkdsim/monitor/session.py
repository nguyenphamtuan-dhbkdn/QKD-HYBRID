"""BB84 lifecycle and its public audit trail."""

import math
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from uuid import uuid4

from qkdsim.config import SessionConfig
from qkdsim.monitor.calibration import Calibration
from qkdsim.monitor.detectors import DetectorDecision, evaluate, qber_p_value
from qkdsim.monitor.events import Event, write_evidence
from qkdsim.monitor.metrics import Metrics, WindowQBER, summarize, window_qber
from qkdsim.monitor.policy import AlertLevel, Policy, SessionUnavailable
from qkdsim.physics.channel import transmittance
from qkdsim.postprocess.estimation import QBERStatistics
from qkdsim.postprocess.sifting import SiftedKey
from qkdsim.protocols.bb84 import BB84Transmission


class State(StrEnum):
    """States in one BB84 attempt and the resulting key lifecycle."""

    INIT = "INIT"
    QUANTUM_TX = "QUANTUM_TX"
    BASIS_RECONCILIATION = "BASIS_RECONCILIATION"
    PARAMETER_ESTIMATION = "PARAMETER_ESTIMATION"
    ERROR_CORRECTION = "ERROR_CORRECTION"
    VERIFICATION = "VERIFICATION"
    PRIVACY_AMPLIFICATION = "PRIVACY_AMPLIFICATION"
    KEY_READY = "KEY_READY"
    KEY_IN_USE = "KEY_IN_USE"
    ABORT = "ABORT"


_NEXT = {
    State.INIT: State.QUANTUM_TX,
    State.QUANTUM_TX: State.BASIS_RECONCILIATION,
    State.BASIS_RECONCILIATION: State.PARAMETER_ESTIMATION,
    State.PARAMETER_ESTIMATION: State.ERROR_CORRECTION,
    State.ERROR_CORRECTION: State.VERIFICATION,
    State.VERIFICATION: State.PRIVACY_AMPLIFICATION,
    State.PRIVACY_AMPLIFICATION: State.KEY_READY,
    State.KEY_READY: State.KEY_IN_USE,
}


class MonitoredSession:
    """Orchestrate state, policy, and public evidence across attempts."""

    def __init__(
        self,
        config: SessionConfig,
        *,
        output: Path | None = None,
        calibration: Calibration | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self.output = output
        self.clock = clock
        self.settings = config.monitor
        if calibration is not None:
            self.settings = replace(self.settings, e0=calibration.qber)
        self.y0 = (
            calibration.detection_rate
            if calibration is not None
            else self._expected_yield()
        )
        self.policy = Policy(self.settings, config.crypto.max_bytes_per_key)
        self.events: list[Event] = []
        self.session_id = uuid4()
        self.state = State.INIT
        self.metrics = Metrics()
        self.windows: tuple[WindowQBER, ...] = ()
        self.detector: DetectorDecision | None = None
        self._ready_at = 0.0
        self._bytes = 0
        self._messages = 0
        self._rekey: str | None = None
        self._emit(None, "session initialized")

    def _expected_yield(self) -> float:
        cfg = self.config.channel
        click = transmittance(cfg.length_km, cfg.alpha_db_per_km) * cfg.eta_det
        if self.config.source.kind == "weak_coherent":
            mu = self.config.source.mu
            assert mu is not None
            click = -math.expm1(-mu * click)
        return click + (1 - click) * cfg.p_dark

    @property
    def directory(self) -> Path | None:
        """A separate artifact directory for each attempt."""
        return self.output / str(self.session_id) if self.output is not None else None

    def _emit(self, previous: State | None, reason: str) -> Event:
        event = Event(
            datetime.now(UTC).isoformat(),
            str(self.session_id),
            previous,
            self.state,
            self.policy.level.name,
            reason,
            self.metrics,
            self.detector,
        )
        self.events.append(event)
        if (directory := self.directory) is not None:
            directory.mkdir(parents=True, exist_ok=True)
            event.append(directory / "events.jsonl")
        return event

    def advance(self, state: State, reason: str) -> None:
        """Advance one legal stage, recording the new state and reason."""
        if _NEXT.get(self.state) != state:
            raise RuntimeError(f"illegal transition {self.state} -> {state}")
        if state == State.KEY_READY:
            self.policy.key_ready()
            self._ready_at = self.clock()
        previous, self.state = self.state, state
        self._emit(previous, reason)

    def start(self) -> None:
        """Start a new attempt, applying rekey and retry admission controls."""
        prior = self.state
        reason = "retry after abort"
        if prior in (State.KEY_READY, State.KEY_IN_USE):
            rekey = self._rekey or self.policy.rekey_reason(
                self._bytes,
                self._messages,
                self.clock() - self._ready_at,
            )
            if rekey is None:
                raise SessionUnavailable("current key can still be used")
            reason = rekey
        elif prior not in (State.INIT, State.ABORT):
            raise SessionUnavailable("session already in progress")
        self.policy.admit(self.clock())
        if prior != State.INIT:
            self.session_id = uuid4()
            self.state = State.INIT
            self.metrics = Metrics()
            self.windows = ()
            self.detector = None
            self._rekey = None
            self._bytes = self._messages = 0
            self._emit(prior, reason)
        self.advance(State.QUANTUM_TX, "transmitting pulses")

    def record_transmission(self, observed: BB84Transmission) -> None:
        """Publish counts available before the basis exchange."""
        sent = observed.detected_mask.size
        detected = int(observed.detected_mask.sum())
        self.metrics = Metrics(
            sent=sent,
            detected=detected,
            double_clicks=observed.double_clicks,
            detection_rate=detected / sent,
            double_click_rate=observed.double_clicks / sent,
        )

    def sample(
        self,
        observed: BB84Transmission,
        sifted: SiftedKey,
        stats: QBERStatistics | None,
    ) -> bool:
        """Measure public observations and return whether the detector alarms."""
        self.metrics, errors = summarize(observed, sifted, stats)
        self.windows = window_qber(errors, self.settings.window_size)
        self.detector = evaluate(
            errors,
            sent=sifted.sent,
            detected=sifted.detected,
            y0=self.y0,
            config=self.settings,
            bb84=self.config.bb84,
        )
        if stats is not None:
            p = qber_p_value(stats.errors, stats.sample_size, self.settings.e0)
            self.policy.observe(self.detector, p)
        return self.policy.level >= AlertLevel.ABORT

    def abort(self, reason: str) -> None:
        """Stop an active attempt and write its public evidence."""
        if self.state not in _NEXT or self.state in (State.INIT, State.KEY_READY):
            raise RuntimeError(f"cannot abort session from {self.state}")
        self.policy.abort(self.clock())
        previous, self.state = self.state, State.ABORT
        event = self._emit(previous, reason)
        if (directory := self.directory) is not None:
            write_evidence(
                directory,
                event,
                self.windows,
                self.settings.e0,
                self.y0,
                self.config.bb84.q_max,
            )

    def authorize_message(self, size_bytes: int) -> None:
        """Charge one message, blocking use when its projected usage needs rekey."""
        if type(size_bytes) is not int or size_bytes < 0:
            raise ValueError("message size must be a nonnegative integer")
        if self.state not in (State.KEY_READY, State.KEY_IN_USE):
            raise SessionUnavailable("session has no usable key")
        bytes_used = self._bytes + size_bytes
        messages = self._messages + 1
        self._rekey = self._rekey or self.policy.rekey_reason(
            bytes_used,
            messages,
            self.clock() - self._ready_at,
        )
        if self._rekey:
            raise SessionUnavailable(self._rekey)
        self._bytes, self._messages = bytes_used, messages
        if self.state == State.KEY_READY:
            self.advance(State.KEY_IN_USE, "first message authorized")
