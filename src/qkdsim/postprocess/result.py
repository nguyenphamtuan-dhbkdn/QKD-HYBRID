"""Key material and abort evidence returned by a BB84 simulation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from qkdsim.postprocess.estimation import QBERStatistics


@dataclass(frozen=True)
class FinalKey:
    """Shared key packed MSB-first with zero padding after length_bits."""

    key_bytes: bytes = field(repr=False)
    key_id: UUID
    session_id: UUID
    length_bits: int
    qber: float
    qber_ub: float
    leak_total: int
    eps_sec: float
    eps_cor: float
    created_at: datetime
    backend: Literal["fast", "qiskit"]
    ground_truth_eve_present: bool = field(repr=False)


@dataclass(frozen=True)
class AbortEvidence:
    """Reason and public parameter-estimation evidence from a failed session."""

    session_id: UUID
    reason: Literal[
        "insufficient statistics",
        "qber above threshold",
        "verification bound exceeds eps_cor",
        "verification mismatch",
        "no secret key at this QBER/length",
        "privacy amplification mismatch",
    ]
    planned_sample_size: int
    stats: QBERStatistics | None
