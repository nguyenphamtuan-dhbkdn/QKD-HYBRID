"""Toeplitz universal hashing over GF(2)."""

import numpy as np
from scipy.signal import fftconvolve  # type: ignore[import-untyped]

from qkdsim.physics.states import BitArray
from qkdsim.postprocess._bits import validate_bits
from qkdsim.rng import secure_random


def random_toeplitz_seed(n_bits: int, out_len: int) -> BitArray:
    """Draw the n_bits + out_len - 1 public Toeplitz bits from OS entropy."""
    if n_bits < 1 or out_len < 1:
        raise ValueError("Toeplitz dimensions must be positive")
    size = n_bits + out_len - 1
    packed = np.frombuffer(secure_random((size + 7) // 8), dtype=np.uint8)
    return np.unpackbits(packed, count=size)


def _validate_toeplitz(bits: BitArray, out_len: int, seed_bits: BitArray) -> None:
    validate_bits(bits)
    validate_bits(seed_bits)
    if bits.size == 0 or type(out_len) is not int or out_len < 0:
        raise ValueError("Toeplitz hashing requires a nonempty input and out_len >= 0")
    if seed_bits.size != bits.size + out_len - 1:
        raise ValueError("expected n_bits + out_len - 1 Toeplitz seed bits")


def toeplitz_hash_fft(bits: BitArray, out_len: int, seed_bits: BitArray) -> BitArray:
    """Compute T*x mod 2 as the valid FFT convolution of seed and x.

    T[i,j] = seed[n-1+i-j]. Round the real convolution to integers before
    reducing modulo two. Time is O((n+out_len)*log(n+out_len)).
    """
    _validate_toeplitz(bits, out_len, seed_bits)
    if out_len == 0:
        return np.empty(0, dtype=np.uint8)
    convolution = np.asarray(
        fftconvolve(seed_bits, bits, mode="valid"), dtype=np.float64
    )
    coefficients = np.rint(convolution).astype(np.int64)
    return np.asarray(coefficients & 1, dtype=np.uint8)


def toeplitz_hash_reference(
    bits: BitArray, out_len: int, seed_bits: BitArray
) -> BitArray:
    """Evaluate sum_j T[i,j]*x[j] mod 2 directly, one row at a time."""
    _validate_toeplitz(bits, out_len, seed_bits)
    out = np.empty(out_len, dtype=np.uint8)
    for row in range(out_len):
        columns = seed_bits[row : row + bits.size][::-1]
        out[row] = np.count_nonzero(bits & columns) % 2
    return out
