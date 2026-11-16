from qkdsim.analysis.quantum_security import security_rows


def test_quantum_security_rows_against_spec_and_nist_strength_classes() -> None:
    rows = {row.primitive: row for row in security_rows()}
    assert set(rows) == {"AES-128", "AES-256", "ChaCha20", "RSA-2048", "ECC P-256"}
    for name, key_bits in (("AES-128", 128), ("AES-256", 256), ("ChaCha20", 256)):
        row = rows[name]
        assert row.key_bits == row.classical_bits == key_bits
        assert row.quantum_attack == "Grover"
        assert row.quantum_query_bits == key_bits / 2
    for name, key_bits, classical in (("RSA-2048", 2048, 112), ("ECC P-256", 256, 128)):
        row = rows[name]
        assert row.key_bits == key_bits
        assert row.classical_bits == classical
        assert row.quantum_attack == "Shor"
        assert row.quantum_query_bits is None
        assert row.quantum_cost_model == "polynomial"
