"""Compare generic key search and Shor attacks for the E15 primitives."""

from dataclasses import dataclass
from typing import Literal

from qkdsim.analysis.theory import grover_effective_bits


@dataclass(frozen=True)
class SecurityRow:
    """Work exponents and their models, with no exponent for Shor's algorithm."""

    primitive: str
    key_bits: int
    classical_bits: int
    quantum_attack: Literal["Grover", "Shor"]
    quantum_query_bits: float | None
    quantum_cost_model: Literal["generic key-search queries", "polynomial"]


def security_rows() -> tuple[SecurityRow, ...]:
    """Map k-bit cipher keys to k/2 Grover bits and RSA/ECC to NIST classes.

    NIST SP 800-57 Part 1 Rev. 5, Table 2 maps a 2048-bit RSA modulus to
    112 bits and a 256-bit ECC group-order size to 128 bits of classical strength.
    """
    symmetric = (("AES-128", 128), ("AES-256", 256), ("ChaCha20", 256))
    asymmetric = (("RSA-2048", 2048, 112), ("ECC P-256", 256, 128))
    return (
        *(
            SecurityRow(
                name,
                bits,
                bits,
                "Grover",
                grover_effective_bits(bits),
                "generic key-search queries",
            )
            for name, bits in symmetric
        ),
        *(
            SecurityRow(name, bits, classical_bits, "Shor", None, "polynomial")
            for name, bits, classical_bits in asymmetric
        ),
    )
