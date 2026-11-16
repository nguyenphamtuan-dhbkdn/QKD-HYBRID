# Rules and Testing Strategy for Coding Agent

## Environment Note (Windows)
- The host OS is **Windows (PowerShell)**.
- In addition to Makefile, always run verification commands directly via uv run (e.g., uv run pytest, uv run ruff check ., uv run mypy --strict src) or provide a 	asks.ps1 helper script so commands work natively on Windows PowerShell without requiring GNU make.

## 0. Rules for the coding agent (read first)

1. **Work milestone by milestone** (Section 16 in SPEC.md). Do not start milestone N+1 until all acceptance criteria of N pass (pytest, uff, mypy).
2. **Never fabricate results.** Every number, table, and figure in docs/ and esults/ must be produced by code in experiments/ and stored as CSV/JSON in esults/. No hard-coded "expected" outputs in reports.
3. **Reproducibility.** All randomness in simulation goes through a single 
umpy.random.Generator created from a seed in the config. Every experiment writes its config + seed + git commit hash + library versions next to its output.
4. **Separate simulation randomness from real cryptographic randomness.** Simulation RNG (seeded, predictable) is used ONLY to simulate physics. Anything that must be unpredictable in the crypto layer (AEAD nonces random parts, session IDs, privacy-amplification seeds, authentication keys in demos) uses secrets/os.urandom. Document clearly: *a key derived from a seeded simulation is not secure in the real world.*
5. **Never log full keys.** Log only key IDs, lengths, and the first 4 hex chars of a SHA-256 fingerprint.
6. **Type hints everywhere, docstrings with the math/formula used, uff + mypy --strict clean.**
7. **Vectorize** the fast backend with NumPy. No Python loops over individual qubits in the fast path.
8. **Do not invent API details** of Qiskit/cryptography/etc. Check the installed version's docs (help(), source) before use. Do not use removed APIs (e.g. qiskit.execute). Pin versions in pyproject.toml.
9. If a requirement is ambiguous, choose the documented default, write the decision in docs/decisions.md, and continue. Do not stop to ask.
10. Be honest in docs about limits: this is a **simulation**; it models physics idealizations and does not provide real-world security.

## 17. Test strategy

- **Unit:** each function with analytic oracles (Section 4.4 and 12.1 in SPEC.md).
- **Statistical tests:** use binomial/normal tolerances (>= 4 sigma) with fixed seeds; document the tolerance; mark @pytest.mark.statistical and allow running them separately.
- **Property-based (hypothesis):** Cascade always converges to equal keys when Q <= 0.1; PA output length; container round trip; nonce uniqueness; HKDF determinism and domain separation (different info -> different keys).
- **Cross-backend equivalence** (fast vs Qiskit).
- **Negative tests:** wrong key, wrong AAD, truncated container, modified header, replayed message, authentication-tag mismatch, abort when l <= 0.
- **Regression of experiment outputs:** store small golden CSVs for tiny configs.
- **Coverage target:** >= 85% on src/qkdsim.
- **Security-hygiene tests:** assert no module logs raw key bytes (grep-based test); assert crypto layer imports secrets/os.urandom and not the simulation RNG.
