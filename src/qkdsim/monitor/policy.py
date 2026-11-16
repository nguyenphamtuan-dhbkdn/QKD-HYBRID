"""Alert severity, key usage limits, and retry admission."""

from enum import IntEnum

from qkdsim.config import MonitorConfig
from qkdsim.monitor.detectors import DetectorDecision


class AlertLevel(IntEnum):
    """Increasing severity for session and key usage policy."""

    OK = 0
    WARN = 1
    ABORT = 2
    LOCKDOWN = 3


class SessionUnavailable(RuntimeError):
    """The policy currently disallows starting a session or using its key."""


class Policy:
    """Track consecutive aborts and apply monotonic-clock back-off."""

    def __init__(self, config: MonitorConfig, max_bytes: int) -> None:
        self.config = config
        self.max_bytes = max_bytes
        self.level = AlertLevel.OK
        self.consecutive_aborts = 0
        self.retry_at = 0.0

    def admit(self, now: float) -> None:
        """Reject new attempts during lockdown or before the back-off expires."""
        if self.level == AlertLevel.LOCKDOWN:
            raise SessionUnavailable("operator reset required")
        if self.consecutive_aborts and now < self.retry_at:
            raise SessionUnavailable("abort back-off active")
        self.level = AlertLevel.OK

    def observe(self, decision: DetectorDecision, qber_p: float) -> None:
        """Warn below the sqrt(alpha) QBER tail, unless the detector alarms."""
        if decision.outcome == "alarm":
            self.level = AlertLevel.ABORT
        elif qber_p < self.config.alpha**0.5:
            self.level = AlertLevel.WARN

    def abort(self, now: float) -> None:
        """Discard the session, wait base*failures, and lock on repeat failures."""
        self.consecutive_aborts += 1
        self.retry_at = now + self.config.backoff_seconds * self.consecutive_aborts
        self.level = (
            AlertLevel.LOCKDOWN
            if self.consecutive_aborts >= self.config.lockdown_after
            else AlertLevel.ABORT
        )

    def key_ready(self) -> None:
        """Clear the abort streak on successful key generation."""
        self.consecutive_aborts = 0
        self.retry_at = 0.0

    def reset(self) -> None:
        """Apply an explicit operator reset."""
        self.key_ready()
        self.level = AlertLevel.OK

    def rekey_reason(self, sent_bytes: int, messages: int, age: float) -> str | None:
        """Return the first exceeded limit or active warning."""
        if self.level >= AlertLevel.WARN:
            return f"alert {self.level.name}"
        if sent_bytes > self.max_bytes:
            return "byte limit exceeded"
        if messages > self.config.max_msgs:
            return "message limit exceeded"
        if age > self.config.max_seconds:
            return "key age limit exceeded"
        return None
