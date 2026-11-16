# QKD-HYBRID: Simulation of BB84 (main) and E91 (comparison) Quantum Key Distribution with Quantum-Based Monitoring, feeding AES-256-GCM and ChaCha20-Poly1305

> **How to use this file.** Put it in the repo root as `SPEC.md` (and copy Section 0 + Section 17 into `AGENTS.md`). Give Codex one milestone at a time (Section 16). Every milestone has acceptance criteria that must pass before moving on.
> The spec is written in English for precision. All end-user documentation and the final report are written in **Vietnamese** (see Section 15).

---

## 0. Rules for the coding agent (read first)

1. **Work milestone by milestone** (Section 16). Do not start milestone N+1 until all acceptance criteria of N pass (`pytest`, `ruff`, `mypy`).
2. **Never fabricate results.** Every number, table, and figure in `docs/` and `results/` must be produced by code in `experiments/` and stored as CSV/JSON in `results/`. No hard-coded "expected" outputs in reports.
3. **Reproducibility.** All randomness in simulation goes through a single `numpy.random.Generator` created from a seed in the config. Every experiment writes its config + seed + git commit hash + library versions next to its output.
4. **Separate simulation randomness from real cryptographic randomness.** Simulation RNG (seeded, predictable) is used ONLY to simulate physics. Anything that must be unpredictable in the crypto layer (AEAD nonces random parts, session IDs, privacy-amplification seeds, authentication keys in demos) uses `secrets`/`os.urandom`. Document clearly: *a key derived from a seeded simulation is not secure in the real world.*
5. **Never log full keys.** Log only key IDs, lengths, and the first 4 hex chars of a SHA-256 fingerprint.
6. **Type hints everywhere, docstrings with the math/formula used, `ruff` + `mypy --strict` clean.**
7. **Vectorize** the fast backend with NumPy. No Python loops over individual qubits in the fast path.
8. **Do not invent API details** of Qiskit/cryptography/etc. Check the installed version's docs (`help()`, source) before use. Do not use removed APIs (e.g. `qiskit.execute`). Pin versions in `pyproject.toml`.
9. If a requirement is ambiguous, choose the documented default, write the decision in `docs/decisions.md`, and continue. Do not stop to ask.
10. Be honest in docs about limits: this is a **simulation**; it models physics idealizations and does not provide real-world security.

---

## 1. Project goals

### 1.1 Primary goal
Build a modular, tested, reproducible Python project that:

1. Simulates **BB84** with an eavesdropper (Eve), channel noise, and photon loss.
2. Adds a **quantum-based monitoring layer** that detects eavesdropping/anomalies using quantum observables (QBER, CHSH value, detection-rate statistics) with proper statistics (confidence bounds, SPRT, CUSUM).
3. Performs full **classical post-processing**: sifting, parameter estimation, Cascade error correction, verification, privacy amplification, finite-key length calculation.
4. Simulates **E91** (entanglement-based, Bell/CHSH test) as the comparison protocol.
5. Feeds the final secret key (through HKDF) into **AES-256-GCM** (baseline) and **ChaCha20-Poly1305** (alternative) and benchmarks them on real data (text, image, binary).
6. Provides a key-management layer (key pool, rekeying policy), an authenticated classical channel, and an end-to-end secure messaging/file demo where Eve can be toggled on and detected.
7. Produces all experiments, figures, and tables needed for a scientific report/thesis in Vietnamese.

### 1.2 Research questions the experiments must answer
- RQ1: How does QBER depend on eavesdropping fraction and channel noise? Does it match theory (25% × p for intercept-resend)?
- RQ2: How reliably and how fast does the monitor detect Eve (detection probability, false-alarm rate, detection delay) as a function of sample size and noise?
- RQ3: How long is the final secret key as a function of pulses sent, QBER, error-correction efficiency, and security parameters (finite-key effect)?
- RQ4: How do BB84 and E91 compare (sifting efficiency, noise tolerance, Eve-detection power, key rate vs distance, implementation cost)?
- RQ5: How do AES-256-GCM and ChaCha20-Poly1305 compare (throughput, latency, integrity guarantees, nonce-misuse behavior) when keyed from QKD?
- RQ6: What is the effective quantum-security level of the symmetric ciphers under Grover, and why is QKD key distribution still needed given Shor?

### 1.3 Non-goals
- No real hardware, no real-network QKD deployment.
- No implementation of attacks beyond: intercept-resend (full/partial), photon-number-splitting (stretch), and MITM on an unauthenticated classical channel (to demonstrate why authentication is mandatory). Detector-blinding/Trojan-horse attacks are **discussed in text only**, not implemented.

---

## 2. Tech stack and environment

- Python **3.11+**, `src/` layout, `pyproject.toml` (PEP 621), dependency management with `uv` or `pip`.
- Runtime deps: `numpy`, `scipy`, `pandas`, `matplotlib`, `qiskit`, `qiskit-aer`, `cryptography` (AEAD + HKDF), `pyyaml`, `typer` (CLI), `rich` (console), `tqdm`.
- Dev deps: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `mypy`, `pre-commit`.
- Optional extras (`[project.optional-dependencies]`): `dashboard` (`streamlit` or `plotly`), `pqc` (`liboqs-python`; may fail to install on some platforms, so it must be strictly optional and guarded by `try/except ImportError`), `api` (`fastapi`, `uvicorn`).
- `Makefile` targets: `setup`, `test`, `lint`, `typecheck`, `experiments`, `figures`, `report`, `demo`.
- GitHub Actions CI (optional): lint + typecheck + tests on 3.11 and 3.12.

---

## 3. Repository layout

```
qkd-hybrid/
├── pyproject.toml
├── Makefile
├── README.md                    # Vietnamese quick start
├── SPEC.md                      # this file
├── AGENTS.md                    # Section 0 + 17
├── configs/
│   ├── default.yaml
│   ├── bb84_noiseless.yaml
│   ├── bb84_eve_full.yaml
│   ├── e91_default.yaml
│   └── experiments/             # one yaml per experiment E1..E15
├── src/qkdsim/
│   ├── __init__.py
│   ├── config.py                # dataclasses + YAML loading + validation
│   ├── rng.py                   # SimRNG (seeded) and secure_random (os.urandom wrappers)
│   ├── physics/
│   │   ├── states.py            # bases, encodings, rotation angles
│   │   ├── channel.py           # loss, depolarizing/bit-flip, dark counts, misalignment
│   │   ├── source.py            # single-photon ideal source; weak coherent pulse (Poisson)
│   │   └── detector.py          # efficiency, dark counts, double-click handling
│   ├── attacks/
│   │   ├── intercept_resend.py  # full and partial (fraction p), fixed or random basis
│   │   ├── pns.py               # STRETCH
│   │   └── mitm_classical.py    # attack on unauthenticated classical channel
│   ├── protocols/
│   │   ├── bb84.py              # fast (NumPy) backend
│   │   ├── bb84_qiskit.py       # Qiskit backend (stabilizer sim)
│   │   ├── bb84_decoy.py        # STRETCH: vacuum+weak decoy
│   │   ├── e91.py               # fast backend (analytic/sampled) 
│   │   ├── e91_qiskit.py        # Qiskit backend
│   │   └── hybrid.py            # OPTIONAL: BB84+E91 combination (K = HKDF(K_bb84 || K_e91))
│   ├── postprocess/
│   │   ├── sifting.py
│   │   ├── estimation.py        # QBER estimate, confidence bounds
│   │   ├── cascade.py           # information reconciliation
│   │   ├── verification.py      # universal-hash key confirmation
│   │   ├── privacy_amp.py       # Toeplitz hashing via FFT
│   │   └── keylength.py         # finite-key secret length calculation
│   ├── monitor/
│   │   ├── metrics.py           # windowed QBER, S, detection rate, sift rate
│   │   ├── detectors.py         # threshold, SPRT, CUSUM, CI-based
│   │   ├── policy.py            # alert levels, abort/rekey policy
│   │   ├── session.py           # session state machine
│   │   └── events.py            # JSONL event log
│   ├── auth/
│   │   ├── channel.py           # AuthenticatedChannel (HMAC-SHA256 baseline)
│   │   └── wegman_carter.py     # STRETCH: information-theoretic MAC with key consumption accounting
│   ├── crypto/
│   │   ├── kdf.py               # HKDF-SHA256 wrappers with domain-separation labels
│   │   ├── aead.py              # AESGCM256, ChaCha20Poly1305 wrappers (uniform interface)
│   │   ├── otp.py               # OPTIONAL: one-time pad with key-budget accounting
│   │   ├── container.py         # encrypted file format (header + chunks)
│   │   └── keystore.py          # key pool, key IDs, rekey policy, ETSI-014-style interface
│   ├── analysis/
│   │   ├── theory.py            # closed-form expectations (QBER, detect prob, CHSH, key rate)
│   │   ├── randomness.py        # NIST SP 800-22 subset + min-entropy estimate
│   │   ├── quantum_security.py  # Grover/Shor effective security table
│   │   └── stats.py             # CIs (Clopper-Pearson, Wilson), bootstrap, binomial tests
│   ├── qrng.py                  # Qiskit Hadamard-measure QRNG vs PRNG (basis selection)
│   └── cli.py                   # typer CLI
├── experiments/
│   ├── e01_qber_vs_eve.py ... e15_*.py
│   ├── run_all.py
│   └── plotting.py              # consistent matplotlib style, saves PNG+PDF (300 dpi)
├── demos/
│   ├── secure_chat.py           # Alice/Bob asyncio sockets + optional Eve proxy
│   ├── file_encrypt_demo.py
│   ├── shor_n15.py              # OPTIONAL motivation (see JST-UD 8256)
│   └── grover_toy.py            # OPTIONAL motivation (see JST-UD 7832)
├── tests/
│   ├── unit/ ...
│   ├── statistical/ ...
│   └── integration/ ...
├── results/                     # generated: csv/, figures/, logs/
├── docs/
│   ├── decisions.md
│   ├── theory_vi.md             # Vietnamese theory notes
│   ├── report_outline_vi.md
│   └── references.bib
└── data/
    └── samples/                 # sample text, small PNG, 10 MB random file generated by script (do not commit large files)
```

---

## 4. Physical and protocol models

### 4.1 Bases and encoding (BB84)
- Basis `0` = rectilinear Z: `|0>`, `|1>`. Basis `1` = diagonal X: `|+>`, `|->`.
- Alice draws `n` random bits `a_i` and random bases `A_i` (uniform by default; configurable bias `p_Z` for efficient-BB84 variant, stretch).
- Bob draws random bases `B_i`. If `A_i == B_i` and no error, Bob's bit equals `a_i`. Otherwise Bob's outcome is uniform random.
- Qiskit circuit per qubit: `if a: X`, `if A==1: H` → (Eve) → `if B==1: H` → measure Z.
  This is **Clifford-only**, so use `AerSimulator(method="stabilizer")` and pack many qubits into **one circuit** (n up to several thousand). Check the installed Aer supports the instruction set used.

### 4.2 Fast backend (NumPy) semantic model
For each pulse i (vectorized):
1. Source: single photon (default) or weak coherent pulse with Poisson photon number `k ~ Poisson(mu)`.
2. Channel: transmittance `eta_ch = 10^(-alpha * L / 10)` with `alpha = 0.2 dB/km` default; each photon survives with probability `eta_ch`. Optical misalignment error `e_d` (default 0.01) flips Bob's outcome with prob `e_d` when bases match (and is irrelevant when mismatched).
3. Eve (Section 5).
4. Detector: efficiency `eta_d` (default 0.1 for realism, 1.0 for ideal tests), dark count probability `p_dark` per gate (default 1e-6, 0 for ideal). Dark counts give uniformly random outcomes. Multiple clicks: assign random bit (squashing model) and record counter.
5. Output: arrays `a, A, B, b_measured, detected_mask`, plus ground-truth arrays for analysis only (`eve_intercepted_mask`, `eve_basis`, `eve_bit`). **Ground truth must never be accessible to protocol/monitor code**: expose through a separate `GroundTruth` object used only by tests/experiments.

### 4.3 Channel noise models (selectable)
- `bitflip(e)`: flip outcome with prob `e`.
- `depolarizing(p)`: with prob `p` replace state by maximally mixed (QBER contribution `p/2`). Implement identically in NumPy and in Qiskit via `NoiseModel` + `depolarizing_error` on identity gates inserted into the circuit.
- `misalignment(theta)`: rotate the state by angle `theta` (optional); QBER contribution `sin^2(theta)` in each basis.
- Provide a function that converts between parameters and the resulting expected QBER, and test it.

### 4.4 Expected values (used as test oracles)
- No Eve, no noise, ideal detection: QBER = 0 exactly.
- Full intercept-resend in random bases (p=1): QBER = 0.25. Partial with fraction p: QBER = 0.25·p (+ channel noise, combine as `e = e_ch + e_eve - 2 e_ch e_eve` for independent flips).
- Sifting efficiency (equal-probability bases) = 1/2 of detected pulses.
- Probability that Eve is caught with `k` compared bits (p=1, no noise): `1 - (3/4)^k`.
- E91 (Section 8): ideal CHSH `|S| = 2√2 ≈ 2.8284`; classical bound 2; Werner visibility `V` gives `S = 2√2·V`, so violation requires `V > 1/√2 ≈ 0.7071`.

---

## 5. Eavesdropper models

All attacks implement a common `Attack` interface: `apply(states_or_arrays, rng) -> modified, ground_truth_info`.

1. **Intercept-resend (IR)**, parameters: `p` (fraction of pulses attacked, default 1.0), `basis_mode` ∈ {`random`, `fixed_Z`, `fixed_X`}. Eve measures in her basis, resends the measured state in that basis. Verify against theory 0.25·p (random basis) and 0.25·p·... for fixed basis (Codex must derive: with fixed Z basis and uniformly random Alice bases, the induced QBER is also 0.25·p on the sifted key; verify by test).
2. **Partial / adaptive IR**: Eve attacks only a random subset, or only after observing that monitoring is lenient (stretch: adaptive Eve that keeps p below a detection threshold; used in experiment E13 to show the monitor's detection delay vs stealth tradeoff).
3. **PNS (stretch, requires weak coherent source)**: Eve splits one photon from every pulse with `k>=2`, forwards the rest; to hide, optionally blocks some single-photon pulses so Bob's detection rate stays unchanged. Used to show why decoy states are needed.
4. **Classical-channel MITM (`mitm_classical.py`)**: Eve sits between Alice and Bob on the classical channel and runs two independent BB84 sessions. With an unauthenticated channel she obtains both keys → demonstrates that authentication is mandatory (experiment E12). With authenticated channel the attack must fail (detected tag mismatch).

---

## 6. BB84 protocol and post-processing (detailed)

### 6.1 Session pipeline (state machine in `monitor/session.py`)
```
INIT → QUANTUM_TX → BASIS_RECONCILIATION (sifting) → PARAMETER_ESTIMATION
     → [QBER_OK?] no → ABORT(reason, evidence)
     → ERROR_CORRECTION (Cascade) → VERIFICATION → PRIVACY_AMPLIFICATION
     → KEY_READY → KEY_IN_USE → (rekey trigger) → INIT
```
Every transition emits a structured JSONL event with timestamp, session id, counters, metrics, and reason.

### 6.2 Sifting
- Bob announces which pulses were detected; Alice and Bob exchange bases (over the authenticated classical channel); keep indices where detected and `A_i == B_i`.
- Output sifted keys `K_A`, `K_B`, and index list. Track counters: sent, detected, sifted.

### 6.3 Parameter estimation
- Randomly choose a subset of size `k = ceil(f_test · n_sift)` (default `f_test = 0.1`; hard minimum `k_min = 200` else abort with "insufficient statistics"), reveal and compare those bits publicly, and **discard** them from the key.
- `Q_est = errors / k`.
- Finite-sample upper bound (simplified Hoeffding; document that rigorous analysis uses Serfling/sampling-without-replacement bounds as in Tomamichel et al. 2012):
  `Q_ub = Q_est + sqrt( ln(1/eps_pe) / (2k) )`, default `eps_pe = 1e-10`.
- Also report Clopper-Pearson and Wilson intervals for the plots.
- **Abort rule:** abort if `Q_ub > Q_max`. Default `Q_max = 0.11` (asymptotic BB84 one-way post-processing threshold, Shor–Preskill). Make configurable; experiments must show the effect of a stricter `Q_max` (e.g. 0.08).

### 6.4 Error correction — Cascade (`cascade.py`)
Implement the Brassard–Salvail Cascade protocol:
- 4 passes (configurable). Pass 1 block size `k1 = max(2, ceil(0.73 / Q_est))`; blocks double each pass (`k_i = 2 k_{i-1}`).
- Each pass applies a fresh random permutation (shared seed via the authenticated classical channel).
- For each block, compare parity; on mismatch, run **BINARY** (bisect) to locate and flip one error; after a correction, perform the **cascade-back** step on earlier passes' blocks containing that bit.
- Count every disclosed parity as 1 leaked bit: `leak_EC`.
- Report `f_EC = leak_EC / (n_key · h2(Q_est))` (typical 1.05–1.25); test that for Q in {0.01, 0.03, 0.05, 0.08} the final reconciled keys are identical with probability ≥ 0.999 and `f_EC < 1.4`.
- Provide a `perfect_EC` ideal mode with `leak = n·h2(Q)·f` (f configurable) for fast large-scale sweeps; flag clearly which mode each experiment used.

### 6.5 Verification
- After EC, compare a hash tag of `v = 64` bits (universal hash: polynomial evaluation over GF(2^61 − 1) with a fresh random secret seed from `secrets`, transmitted on the authenticated channel). Mismatch → abort or rerun EC. Count `v` bits in `leak_verify`. `eps_cor ≈ 2^-v` order; document.

### 6.6 Privacy amplification (`privacy_amp.py`)
- Toeplitz-matrix universal hashing: output `K = T · x (mod 2)`, `T` is `l × n` Toeplitz defined by `n + l − 1` seed bits (from `secrets`, exchanged on the authenticated channel).
- **Efficient implementation required**: matrix-vector product via FFT convolution (`scipy.signal.fftconvolve` on integer arrays then `mod 2` with rounding) so n up to ≥ 1e6 runs in seconds. Explicitly forming T is forbidden for n > 4096. Add a slow reference implementation and test equality on small sizes.
- Include a test that the output length equals `l` and that flipping one input bit changes ~50% of the output bits (avalanche sanity check, statistical).

### 6.7 Secret key length (`keylength.py`)
Given `n_key` (reconciled bits used for the key), `Q_ub`, `leak_EC`, `leak_verify`, `eps_sec`, `eps_cor`:

```
l = floor( n_key · (1 − h2(Q_ub)) − leak_EC − leak_verify − 2·log2(1/eps_PA) )   (simplified)
```
where `h2(x) = −x log2 x − (1−x) log2(1−x)`, `eps_PA` ≈ `eps_sec`. If `l <= 0` abort ("no secret key at this QBER/length"). **The docstring must state this is a simplified composable-style bound** and cite the assumptions (collective/coherent attack security via Shor–Preskill-style entropy bound for ideal single-photon source). Provide an `asymptotic` variant `l = n_key (1 − (1 + f_EC) h2(Q))` for comparison plots.

### 6.8 Output
`FinalKey(bytes, key_id, session_id, length_bits, qber, qber_ub, leak_total, eps_sec, eps_cor, created_at, backend, ground_truth_eve_present: bool)` — the last field only for experiment bookkeeping and absent in the object passed to the crypto layer.

---

## 7. The quantum-based monitoring layer (the "solution" component)

This is the project's main original contribution; treat it as a first-class module with its own experiments (E2, E3, E13, E14).

### 7.1 Observables monitored
1. **QBER** on the public test subset (per block/window and cumulative).
2. **Detection rate / loss**: `detected / sent` vs the calibrated expectation `Y = eta_ch·eta_d + p_dark`. A sudden drop or rise indicates blocking, PNS-style loss compensation, or hardware faults.
3. **Basis-conditional error rates**: `QBER_Z` vs `QBER_X`. Strong asymmetry flags a basis-dependent attack (e.g. fixed-basis Eve).
4. **CHSH S-value** (E91 mode) with its standard error.
5. **Sifting ratio** vs expected 1/2.
6. **Double-click rate** and **dark-count proxy** (events when no photon was sent—simulate "empty" calibration pulses).

### 7.2 Detectors (`monitor/detectors.py`) — implement all and compare
1. **Fixed threshold:** `Q_ub > Q_max` (baseline).
2. **Confidence-interval test:** alert when the lower Clopper-Pearson bound of QBER exceeds the calibrated noise floor `e_0` (controls false alarms explicitly: `alpha`).
3. **SPRT (Wald's sequential probability ratio test):** `H0: e = e_0` (honest channel) vs `H1: e = e_1` (attack-level, e.g. `e_0 + 0.25·p_min`). Log-likelihood ratio per compared bit: `+log(e1/e0)` for an error, `+log((1−e1)/(1−e0))` for a match. Thresholds `A = log((1−β)/α)`, `B = log(β/(1−α))`. Report detection delay (number of compared bits until decision) distributions.
4. **CUSUM** on windowed error indicators to detect drifts or an Eve who switches on mid-session.
5. **Joint test** combining QBER + detection-rate anomaly (Fisher's method or max-statistic with Bonferroni). Document the false-alarm budget.

### 7.3 Calibration
- Before sessions, run a **calibration phase** (no-Eve assumption, e.g. 1e5 pulses) to estimate baseline `e_0`, `Y_0`, and variance; store in `calibration.json`. Experiments must show what happens if calibration is contaminated by Eve (stretch).

### 7.4 Policy engine (`policy.py`)
- Alert levels: `OK`, `WARN` (statistic elevated but below abort), `ABORT` (discard key material from this session), `LOCKDOWN` (repeated aborts → stop sending, require operator reset).
- Rekey policy: rekey when any of: bytes encrypted > `max_bytes_per_key` (default 2^30 bytes), age > `max_seconds`, number of messages > `max_msgs`, or alert level ≥ `WARN`.
- Rate limiting/back-off after aborts.

### 7.5 Evidence report
On ABORT, write `evidence.json`: counters, QBER per window, CI values, detector decisions, plots. This is what the report shows as "detected Eve" demonstration.

### 7.6 Metrics for the monitor (experiments)
- Detection probability vs (p, e_ch, sample size k).
- False-alarm rate vs threshold under noise-only runs (≥ 10,000 Monte Carlo sessions per point for tight CIs; use fast backend).
- ROC curves (TPR vs FPR) sweeping `Q_max` for several (p, e_ch).
- Detection delay distribution for SPRT vs fixed-sample test.

---

## 8. E91 protocol (comparison protocol)

### 8.1 Setup
- Source distributes entangled pairs. Use `|Φ+> = (|00> + |11>)/√2` (prepared in Qiskit via `H` on qubit 0 then `CX(0,1)`). Document that Ekert's original uses the singlet; the formulas below are for `|Φ+>` and **must be verified numerically** in tests.
- Measurement along Bloch direction `n(φ) = (sin φ, 0, cos φ)` is implemented by applying `Ry(−φ)` then measuring in Z (check sign convention by test).
- Angles (Bloch angles): Alice `a ∈ {0, π/4, π/2}`, Bob `b ∈ {π/4, π/2, 3π/4}`. Each party picks uniformly at random per pair.
- For `|Φ+>`, correlation `E(φ_A, φ_B) = cos(φ_A − φ_B)`.

### 8.2 Key and test pairs
- **Key pairs**: (a=π/4, b=π/4) and (a=π/2, b=π/2): outcomes perfectly correlated for `|Φ+>` (equal bits; if implementing the singlet, Bob flips). Probability of a key pair per round: 2/9.
- **CHSH pairs**: `(a=0, b=π/4)`, `(a=0, b=3π/4)`, `(a=π/2, b=π/4)`, `(a=π/2, b=3π/4)`.
  `S = E(a0,b1) − E(a0,b3) + E(a2,b1) + E(a2,b3)`. Verify noiseless `S = 2√2` numerically (with the Φ+ conventions above this combination gives +2√2; if sign differs, adapt and document).
- Remaining 3/9 combinations: discarded.
- Compute `S` with standard error via error propagation; alert if `S − z·σ_S ≤ 2` (default `z = 5`).

### 8.3 Noise/Eve in E91
- Werner-state noise: with prob `1−V` replace the pair by white noise. Expect `S = 2√2 V` and key-pair QBER ≈ `(1−V)/2` (verify numerically).
- Eve: intercept-resend on the qubit sent to Bob (measure in random basis from {Z, X} or in one of Bob's angles, resend). Show numerically that `S ≤ 2` (no Bell violation) and key QBER rises. Report the exact numbers obtained, do not assume.
- Loss: coincidence only if both photons arrive: `η_A·η_B`.

### 8.4 Post-processing
Same pipeline as BB84 (estimation → Cascade → verification → PA → keylength) applied to key pairs, with an additional security condition: `S` must violate CHSH by the margin above, otherwise abort. Document that full device-independent security analysis is out of scope.

### 8.5 Comparison metrics (experiment E8)
Sifting efficiency (BB84: 1/2; E91 original: 2/9 key + 4/9 CHSH), noise tolerance (QBER and visibility thresholds), Eve detection power (QBER-only vs QBER+CHSH), source/hardware complexity (qualitative table), key rate vs distance (model), simulation cost.

---

## 9. Optional hybrid BB84 + E91 mode (`protocols/hybrid.py`)
Motivated by the "hybrid BB84/E91" literature the user is reviewing. Implement two clearly separated variants and compare:
- **H1 (key combination):** `K = HKDF(K_bb84 || K_e91, info="hybrid-v1")` — secure if at least one component is secure (document the argument).
- **H2 (monitoring fusion):** run BB84 for key generation and use E91 Bell test as an independent channel-health monitor; alert if either QBER or S fails.
Report key rate overhead and detection improvement. Mark as OPTIONAL; implement after core milestones.

---

## 10. Authenticated classical channel (`auth/`)

- Baseline: `AuthenticatedChannel` using HMAC-SHA256 with a pre-shared initial key `K_auth0`, message counters to prevent replay, and message framing (JSON or msgpack-free simple binary).
- Account for authentication key consumption: each session consumes `auth_bits`; replenish the pool from QKD output (set aside the first `m` bits of each final key). Track `net_key_rate = (l − auth_consumption)/pulses`.
- STRETCH: Wegman-Carter MAC with one-time key (Toeplitz or polynomial hashing) to give an information-theoretic tag, with `eps_auth`.
- Experiment E12: MITM without authentication succeeds (Eve shares a key with each side; ground truth shows both keys known to Eve) vs with authentication fails (tag mismatch → session aborted). This is mandatory because it is a standard weak point in naive BB84 write-ups.

---

## 11. Cryptographic layer

### 11.1 Key derivation (`kdf.py`)
- `final_key (bytes) → HKDF-SHA256` (library implementation, `cryptography.hazmat.primitives.kdf.hkdf`) with salt = session-bound random (from `secrets`, transmitted in the header) and `info` labels for domain separation:
  `b"qkd-hybrid/v1/aes256gcm"`, `b"qkd-hybrid/v1/chacha20poly1305"`, `b"qkd-hybrid/v1/auth"`, `b"qkd-hybrid/v1/otp"`.
- Require `len(final_key) >= 32` bytes; otherwise abort the session or concatenate multiple QKD sessions (key pool).

### 11.2 AEAD wrappers (`aead.py`)
Uniform interface:
```python
class Aead(Protocol):
    name: str
    key_size: int
    nonce_size: int
    tag_size: int
    def encrypt(self, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes: ...
    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes: ...
```
- Implementations: `AesGcm256` and `ChaCha20Poly1305` via `cryptography`. 96-bit nonces.
- **Nonce discipline:** 96-bit nonce = 32-bit random per-key prefix || 64-bit counter. Enforce a per-key message limit (`2^32` messages hard cap; far lower default) and raise `NonceExhaustedError`. Never accept caller-provided nonces in the high-level API (only in the low-level test hooks and the nonce-reuse demo).
- AAD always includes: container version, cipher id, session id, key id, sequence number, chunk index, final-chunk flag.

### 11.3 Container format (`container.py`)
```
magic "QKDH" | version u8 | cipher_id u8 | session_id 16B | key_id 16B | hkdf_salt 16B
| nonce_prefix 4B | chunk_size u32 | orig_size u64 | chunks...
chunk = counter u64 | ciphertext (<= chunk_size) | tag 16B
```
- Chunk size default 64 KiB. Final chunk flagged in AAD to prevent truncation. Chunk reordering/duplication must be detected (counter in AAD).
- Provide streaming encrypt/decrypt for files larger than RAM.

### 11.4 Optional OTP mode (`otp.py`)
One-time pad using QKD bits directly, with strict **key budget accounting** (each byte used once, then zeroized/marked consumed) plus an authentication tag from the Wegman-Carter or HMAC stretch. Shows the information-theoretic end of the QKD design space; benchmark key consumption vs message size.

### 11.5 Key store / KMS (`keystore.py`)
- Key pool with FIFO of `FinalKey` objects, status (`available`, `reserved`, `used`, `revoked`), `key_id` (UUID4), TTL.
- API: `get_status()`, `get_key(size)`, `get_key_with_id(key_id)` modelled on the ETSI GS QKD 014 concepts (verify naming against the standard; mention in docs that this is "ETSI-style", not conformant).
- STRETCH: FastAPI wrapper (`api` extra) exposing the same on localhost for the chat demo.

### 11.6 Optional post-quantum hybrid key combiner (STRETCH, guarded)
If `liboqs-python` is installed: `K = HKDF(K_qkd || K_kem)` where `K_kem` is from an ML-KEM (Kyber) encapsulation. If not installed, the feature must be disabled with a clear message. This shows defense-in-depth (QKD + PQC) in the discussion section.

---

## 12. Analysis modules

### 12.1 Theory (`analysis/theory.py`)
Closed forms with docstrings and tests: `qber_ir(p, e_ch)`, `p_detect_ir(k, p)`, `chsh_werner(V)`, `h2(x)`, `asymptotic_key_fraction(Q, f_EC)`, `qber_threshold_bb84()` (~0.11 numerically by solving `1 − 2 h2(Q) = 0` for the ideal-EC case ≈ 0.110), `visibility_threshold_chsh()` = `1/√2`, `grover_effective_bits(k) = k/2`.

### 12.2 Quantum security table (`quantum_security.py`)
Output a CSV used in the report:
| Primitive | Classical security (bits) | Best-known quantum attack | Effective (bits) | Note |
|---|---|---|---|---|
| AES-128 | 128 | Grover | ~64 (query model) | see Grassl et al. 2016 for circuit cost |
| AES-256 | 256 | Grover | ~128 | |
| ChaCha20 (256-bit key) | 256 | Grover | ~128 | |
| RSA-2048 | ~112 | Shor | broken (polynomial) | motivates QKD/PQC |
| ECC P-256 | ~128 | Shor | broken | |
Fill numbers by code from key sizes; text notes written in the docs with references. Do not claim more than the sources support: state that Grover parallelization and real quantum circuit depth reduce the practical threat and refer to the literature.

### 12.3 Randomness tests (`randomness.py`)
- Implement (from the NIST SP 800-22 definitions) at least: frequency (monobit), block frequency, runs, longest run in a block, serial/approximate entropy (simplified). Also a most-common-value min-entropy estimator.
- Apply to: raw sifted key, final key, PRNG vs Qiskit-QRNG outputs (Section 13).
- Statistical tests on simulated data show "no detectable bias"; they do not prove security. State this in the docs.

### 12.4 Statistics (`stats.py`)
Wilson, Clopper-Pearson, bootstrap percentile CI, two-sided binomial test, helper to run `R` Monte Carlo repetitions with independent child seeds (`SeedSequence.spawn`) and aggregate mean ± CI.

---

## 13. Additional components that add novelty (choose in this priority order)

1. **Finite-key analysis** (Section 6.7) and the plot "secret key rate vs number of pulses" showing the finite-size penalty.
2. **Quantum-based monitoring with SPRT/CUSUM/ROC** (Section 7). Core contribution.
3. **Realistic loss model and key-rate-vs-distance curves** for BB84 (weak coherent, with and without decoy) vs E91 (entangled source).
4. **Decoy-state BB84 (vacuum + weak decoy), STRETCH.**
   - Gain/error: `Q_mu = Y0 + 1 − exp(−eta·mu)`, `E_mu·Q_mu = e0·Y0 + e_d (1 − exp(−eta·mu))` with `e0 = 1/2`.
   - GLLP-style rate: `R ≥ q { −Q_mu f(E_mu) h2(E_mu) + Q_1 [1 − h2(e_1)] }` with `q = 1/2` (basic BB84).
   - Vacuum+weak decoy bounds (Ma, Qi, Zhao, Lo, PRA 72, 012326 (2005)): lower bound on `Y1` and upper bound on `e1` from gains of signal `mu`, decoy `nu`, vacuum. **Codex must look up and verify the exact formulas from the paper before implementing; add a unit test that the bounds reduce to the true `Y1`, `e1` in the infinite-decoy/ideal limit.**
   - Show the PNS attack collapses the naive-BB84 key rate while decoy BB84 recovers a positive rate.
5. **QRNG-based basis selection (`qrng.py`)**: generate random bits by preparing `|0>`, applying `H`, measuring in Qiskit; compare with `numpy`/`secrets` using the Section 12.3 tests and use them as basis source in a BB84 run. Note honestly that the Aer simulator's randomness is pseudo-random, so this demonstrates the *circuit*, not true randomness.
6. **Key management + rekeying policy** driven by the monitor (Section 7.4, 11.5).
7. **Secure chat demo with live Eve toggle** (Section 14, demo D1).
8. **Nonce-misuse and tamper experiments** on both AEADs (E11): demonstrate that reusing a (key, nonce) pair with synthetic data leaks the XOR of plaintexts for ChaCha20/GCM keystream, and that any bit flip yields `InvalidTag`. Educational, synthetic data only, flagged "do not do this" in the report.
9. **Hybrid BB84+E91 mode** (Section 9).
10. **Optional PQC combiner** (Section 11.6).
11. **Optional motivation demos:** Grover on a 3-qubit toy search (JST-UD 7832), Shor factoring N = 15 (JST-UD 8256) with Qiskit, only to motivate "why QKD / why 256-bit symmetric keys". Keep clearly separated in `demos/` and low priority.

---

## 14. Experiments (each: config yaml, script, CSV, PNG+PDF figure, short Vietnamese interpretation stub)

General: repetitions `R = 30` for heavy points, `R = 1000+` for cheap fast-backend points; report mean ± 95% CI; seeds via `SeedSequence`. Use the fast backend for sweeps and the Qiskit backend for validation points.

| ID | Experiment | Sweep | Metric | Expectation to verify |
|---|---|---|---|---|
| E1 | QBER vs Eve fraction | `p ∈ {0,0.05,…,1}`, `n = 1e5`, `e_ch = 0` and `0.02` | measured QBER | `0.25p` (+noise combo) |
| E2 | Noise tolerance & abort | `e_ch ∈ [0, 0.15]`, no Eve | abort rate, key length | abort near 0.11 (finite-size shifts it) |
| E3 | Detection probability vs sample size | `k ∈ {5,10,20,50,100,200}`, `p=1`, `e_ch=0` | P(detect) | `1−(3/4)^k` |
| E4 | Key length pipeline | `n ∈ {1e3…1e6}`, `Q ∈ {0.01,0.03,0.05,0.08}` | sifted, after EC, final length, `f_EC` | monotone, consistent with Section 6.7 |
| E5 | Finite-key penalty | `n` sweep, fixed Q | rate = l/n vs asymptotic | rate approaches asymptotic as n grows |
| E6 | Key rate vs distance | `L ∈ [0,150] km`, `alpha=0.2 dB/km`, `eta_d=0.1`, `p_dark=1e-6` | R per pulse; BB84 vs decoy BB84 vs E91 | exponential decay; cutoff distance reported |
| E7 | E91 CHSH vs noise and Eve | `V ∈ [0.5,1]`; Eve IR | `S`, QBER, abort | `S=2√2 V`; `S ≤ 2` under IR |
| E8 | BB84 vs E91 comparison table | fixed params | sifting eff., tolerance, detection, rate | table + discussion |
| E9 | Cipher benchmark | sizes `{1 KiB…256 MiB}` (cap via config), types: text, PNG, random | throughput MB/s, latency, median + IQR over ≥ 30 runs after warm-up | report honestly; discuss hardware AES-NI dependence |
| E10 | End-to-end pipeline | text, image, 10 MB file, both ciphers | success, integrity, timings per stage | decrypt equals original (hash equal) |
| E11 | Tamper & nonce-misuse | bit flips (header/ct/tag), truncation, reorder, nonce reuse | detection rate, leak demo | 100% tamper detection |
| E12 | MITM with/without auth | 1000 sessions | success rate of Eve | w/o auth: ~100%; with auth: ~0% |
| E13 | Monitor detectors compare | `p ∈ {0.05…1}`, noise levels | TPR/FPR, ROC, SPRT delay, adaptive Eve | SPRT needs fewer bits for the same error rates |
| E14 | Randomness tests | raw/final key, PRNG vs QRNG circuit | p-values / pass rate | no detectable bias |
| E15 | Quantum security table | key sizes | CSV table | per Section 12.2 |
| E16 (stretch) | PNS vs decoy | `mu`, distance | key rate collapse/recovery | per Section 13.4 |
| E17 (stretch) | Hybrid H1/H2 | combos | key rate, detection | per Section 9 |

Figure rules: Vietnamese axis labels and titles (configurable switch to English), same color scheme per protocol across all figures, error bars/bands, saved at 300 dpi as PNG and as vector PDF, filename `E{nn}_{slug}.png`.

### Demos
- **D1 `secure_chat.py`**: asyncio TCP; Alice/Bob run QKD sessions over the authenticated classical channel (the quantum channel is simulated in-process); messages encrypted with the chosen AEAD; rekey every `N` messages or on alert. Optional `--eve` proxy toggles an attack live; the monitor must abort and show the evidence report; chat refuses to send until a new clean key exists.
- **D2 `file_encrypt_demo.py`**: CLI: `qkdsim encrypt --in file --cipher chacha20|aes256gcm` / `decrypt`; shows key provenance (session id, QBER, key length).
- **D3 Streamlit/plotly dashboard (optional)**: live QBER window, alert level, key pool status.

---

## 15. Documentation deliverables (Vietnamese, in `docs/`)

1. `README.md`: cài đặt, chạy nhanh, cấu trúc thư mục, cách tái lập kết quả.
2. `theory_vi.md`: qubit, cơ sở đo, định lý không nhân bản, BB84, E91, CHSH, QBER, Cascade, khuếch đại riêng tư, AEAD, Grover/Shor — mỗi phần có công thức và liên hệ với code.
3. `report_outline_vi.md` and generated figure/table includes:
   1. Mở đầu (mối đe dọa lượng tử; ý nghĩa JST-UD 7832, 8256)
   2. Tổng quan tài liệu (bảng so sánh các bài báo người dùng cung cấp: BB84+AES-256 hybrid framework, AES-256 chống tấn công lượng tử, E91, multi-layered security with QKD, hybrid BB84/E91 review)
   3. Cơ sở lý thuyết
   4. Thiết kế hệ thống và giải pháp giám sát lượng tử
   5. Cài đặt mô phỏng (kiến trúc, backend, kiểm thử)
   6. Kết quả thực nghiệm E1–E15 và thảo luận
   7. Phân tích bảo mật và hạn chế (mô phỏng ≠ phần cứng thật; side-channel, detector blinding, Trojan-horse chỉ thảo luận; xác thực kênh cổ điển; giả định nguồn đơn photon)
   8. Kết luận và hướng phát triển
4. `decisions.md`: every default choice with rationale.
5. `references.bib` with at least the following (Codex: verify bibliographic details from reliable sources before finalizing; do not invent DOIs):
   - Bennett & Brassard (1984) BB84; Ekert (1991) PRL 67, 661; Shor & Preskill (2000) PRL 85, 441; Gottesman–Lo–Lütkenhaus–Preskill (2004) GLLP; Hwang (2003) / Lo–Ma–Chen (2005) / Ma–Qi–Zhao–Lo (2005) decoy state; Brassard & Salvail (1993) Cascade; Wegman & Carter (1981); Tomamichel–Lim–Gisin–Renner (2012) finite-key; Scarani et al. (2009) RMP; Clauser–Horne–Shimony–Holt (1969); Grover (1996); Shor (1994); Grassl–Langenberg–Roetteler–Steinwandt (2016); Bernstein (ChaCha), RFC 8439; NIST SP 800-38D (GCM); NIST SP 800-22; RFC 5869 (HKDF);
   - Vietnamese sources: Dụng Văn Lữ & Lê Lệ Hằng (2022), JST-UD 20(7):111–116; Dụng Văn Lữ et al. (2023), JST-UD 21(3):104–109;
   - The five PDFs supplied by the user (Quantum-Classical Hybrid Encryption Framework Based on Simulated BB84 and AES-256; The AES-256 Cryptosystem Resists Quantum Attacks; The Quantum Key Distribution Protocol E91; Multi-layered security system integrating QKD; A comprehensive review on the hybrid BB84/E91 QKD protocol). Fill authors/years from the PDFs placed in `docs/papers/` (not committed if copyrighted). **Do not summarize a paper you have not been given.**

---

## 16. Milestones and acceptance criteria

### M0 — Scaffolding
Repo layout, `pyproject.toml`, Makefile, config loader, `SimRNG`, `secure_random`, CLI skeleton, CI, one passing dummy test.
**Accept:** `make lint typecheck test` green; `qkdsim --help` works.

### M1 — Physics core + BB84 fast backend + IR attack
`physics/*`, `attacks/intercept_resend.py`, `protocols/bb84.py`, `postprocess/sifting.py`, `estimation.py`, `analysis/theory.py`, `analysis/stats.py`.
**Accept:**
- Noiseless/no-Eve QBER == 0 over 100 seeds.
- IR p=1: measured QBER within 4σ binomial of 0.25 for n_test ≥ 1e4; p=0.5 → 0.125.
- Sifting ratio ≈ 0.5 (within 4σ).
- Ground truth not importable from protocol modules (enforced by a test that inspects imports).

### M2 — Qiskit backend for BB84
`bb84_qiskit.py` with stabilizer simulator, noise via `NoiseModel`.
**Accept:** for n = 2000, results from both backends agree statistically (two-sample test p > 0.001 across several configs: no Eve, p=1, depolarizing noise). Document runtime scaling.

### M3 — Post-processing
Cascade, verification, Toeplitz-FFT PA, key length, `FinalKey`.
**Accept:**
- Cascade success ≥ 99.9% for Q ∈ {0.01,0.03,0.05,0.08}, `f_EC < 1.4`.
- FFT PA equals reference on random small cases (≥ 1000 cases).
- n = 1e6 PA completes in < 30 s on a laptop.
- End-to-end function `run_bb84_session(config) -> FinalKey | AbortEvidence` works; Alice/Bob final keys identical.

### M4 — Monitor
Metrics, detectors (threshold, CI, SPRT, CUSUM), policy, session state machine, event log, evidence report.
**Accept:**
- Under honest noise e_ch=0.02, false alarm rate ≤ configured α (+ CI slack) in ≥ 10,000 Monte Carlo sessions.
- Under IR p=1, detection rate ≥ 99.9% for k ≥ 200.
- SPRT empirical error rates within tolerance of (α, β).
- JSONL logs validate against a schema (`jsonschema` test).

### M5 — Authenticated channel & MITM
`auth/`, `attacks/mitm_classical.py`.
**Accept:** E12 reproduces: unauth MITM success ~100% (ground-truth check that Eve knows both keys), authenticated MITM success 0/1000.

### M6 — Crypto layer
KDF, AEAD wrappers, container, key store.
**Accept:**
- Known-answer tests against RFC 8439 (ChaCha20-Poly1305) and NIST/ RFC GCM test vectors via the library.
- Round trip for random sizes 0 B … 5 MiB; tamper/truncate/reorder → exception 100%.
- Nonce uniqueness property test (hypothesis) over 1e5 messages.
- Large-file streaming works with constant memory (assert via `tracemalloc` threshold).

### M7 — E91
`e91.py` + Qiskit version, CHSH, noise/Eve, key pipeline.
**Accept:** noiseless `S` within 4σ of 2√2; `S = 2√2·V` for V ∈ {0.6,0.8,0.9,1} within tolerance; IR Eve gives `S ≤ 2` (report measured); key QBER ≈ `(1−V)/2` verified or the discrepancy explained in `decisions.md`.

### M8 — Analysis, randomness, quantum security table, QRNG
**Accept:** unit tests for tests-suite against known random/biased sequences; CSV for E15 generated.

### M9 — Experiments E1–E15 + figures
`experiments/run_all.py` reproduces all CSV/figures from scratch given the configs; runtime documented (quick mode ≤ 15 min, full mode documented).
**Accept:** every figure has CSV provenance; seed + commit recorded; expectations in Section 14 table are either met or the discrepancy analysis is written.

### M10 — Demos + docs + report assets
D1, D2 (and D3 optional), Vietnamese docs, `references.bib`, final report outline with auto-included figures.
**Accept:** fresh clone → `make setup test experiments demo` works following README only.

### M11+ — Stretch (only if M0–M10 are done)
Decoy-state BB84 + PNS (E16), hybrid H1/H2 (E17), Wegman-Carter MAC, PQC combiner, FastAPI KMS, dashboard, Grover/Shor motivation demos.

---

## 17. Test strategy

- **Unit:** each function with analytic oracles (Section 4.4 and 12.1).
- **Statistical tests:** use binomial/normal tolerances (≥ 4σ) with fixed seeds; document the tolerance; mark `@pytest.mark.statistical` and allow running them separately.
- **Property-based (hypothesis):** Cascade always converges to equal keys when `Q ≤ 0.1`; PA output length; container round trip; nonce uniqueness; HKDF determinism and domain separation (different `info` → different keys).
- **Cross-backend equivalence** (fast vs Qiskit).
- **Negative tests:** wrong key, wrong AAD, truncated container, modified header, replayed message, authentication-tag mismatch, abort when `l ≤ 0`.
- **Regression of experiment outputs:** store small golden CSVs for tiny configs.
- **Coverage target:** ≥ 85% on `src/qkdsim`.
- **Security-hygiene tests:** assert no module logs raw key bytes (grep-based test); assert crypto layer imports `secrets`/`os.urandom` and not the simulation RNG.

---

## 18. Key interfaces (guidance; keep names stable)

```python
# config.py
@dataclass(frozen=True)
class ChannelConfig: length_km: float; alpha_db_per_km: float; e_misalign: float; depol: float; eta_det: float; p_dark: float
@dataclass(frozen=True)
class AttackConfig: kind: Literal["none","ir","pns"]; p: float; basis_mode: Literal["random","fixed_z","fixed_x"]
@dataclass(frozen=True)
class BB84Config: n_pulses: int; p_z: float; test_fraction: float; q_max: float; eps_pe: float; eps_sec: float; eps_cor: float; ec_mode: Literal["cascade","ideal"]; f_ec_ideal: float; backend: Literal["fast","qiskit"]
@dataclass(frozen=True)
class E91Config: n_pairs: int; visibility: float; z_chsh: float; ...
@dataclass(frozen=True)
class MonitorConfig: detector: Literal["threshold","ci","sprt","cusum","joint"]; alpha: float; beta: float; e0: float; e1: float; ...
@dataclass(frozen=True)
class CryptoConfig: cipher: Literal["aes256gcm","chacha20poly1305","otp"]; chunk_size: int; max_bytes_per_key: int

# protocols
def run_bb84_session(cfg: SessionConfig, rng: Generator) -> SessionResult   # FinalKey | AbortEvidence + events
def run_e91_session(cfg: SessionConfig, rng: Generator) -> SessionResult

# postprocess
def cascade_reconcile(key_a: NDArray[np.uint8], key_b: NDArray[np.uint8], q_est: float, rng, channel: AuthenticatedChannel) -> CascadeResult  # key_b_corrected, leak_bits, passes, parities_disclosed
def toeplitz_hash_fft(bits: NDArray[np.uint8], out_len: int, seed_bits: NDArray[np.uint8]) -> NDArray[np.uint8]
def secret_key_length(n_key: int, q_ub: float, leak_ec: int, leak_verify: int, eps_sec: float, eps_cor: float) -> int

# crypto
def derive_keys(final_key: bytes, salt: bytes, ciphers: Sequence[str]) -> dict[str, bytes]
def encrypt_file(path_in: Path, path_out: Path, cipher: str, key: bytes, session_meta: SessionMeta) -> EncryptionReport
def decrypt_file(path_in: Path, path_out: Path, key_provider: Callable[[bytes], bytes]) -> DecryptionReport
```

CLI examples (must exist):
```
qkdsim bb84 --config configs/bb84_eve_full.yaml
qkdsim e91 --config configs/e91_default.yaml
qkdsim monitor --config configs/default.yaml --detector sprt
qkdsim encrypt --in data/samples/photo.png --out photo.qkdh --cipher chacha20
qkdsim decrypt --in photo.qkdh --out photo_dec.png
qkdsim experiment E1 --quick
qkdsim experiments --all
```

---

## 19. Default parameters (put in `configs/default.yaml`)

```yaml
seed: 20260116
bb84:
  n_pulses: 200000
  p_z: 0.5
  test_fraction: 0.1
  k_min: 200
  q_max: 0.11
  eps_pe: 1.0e-10
  eps_sec: 1.0e-9
  eps_cor: 1.0e-12
  ec_mode: cascade
  backend: fast
channel:
  length_km: 0
  alpha_db_per_km: 0.2
  e_misalign: 0.01
  depol: 0.0
  eta_det: 1.0
  p_dark: 0.0
attack:
  kind: none
  p: 0.0
  basis_mode: random
e91:
  n_pairs: 200000
  visibility: 1.0
  chsh_z: 5.0
monitor:
  detector: sprt
  alpha: 1.0e-3
  beta: 1.0e-3
  e0: 0.02
  e1: 0.10
crypto:
  cipher: aes256gcm
  chunk_size: 65536
  max_bytes_per_key: 1073741824
```
Note: when `e_misalign = 0.01` the honest QBER floor is ~1%; for ideal-theory tests use a config with all non-idealities zero.

---

## 20. Honest-limitations checklist (must appear in the report)

- Single-photon-source idealization (weak coherent pulses introduce PNS; decoy states mitigate).
- Simplified finite-key bound; no full composable proof for coherent attacks beyond cited results.
- Classical channel must be authenticated; initial pre-shared key is required (QKD "expands" keys).
- Simulation RNG is predictable; real deployments need physical randomness.
- Implementation side channels (detector blinding, Trojan horse, timing) not modelled.
- AEAD security depends on nonce discipline and key lifetime, independent of QKD.
- No real network/hardware evaluation; numbers are model outputs, not measurements.

---

## 21. Kickoff prompts for Codex (copy one at a time)

**Prompt M0–M1**
> Read SPEC.md fully. Implement Milestones M0 and M1 only. Follow Section 0 rules. Create the repo layout, config loader, RNG module, physics core, BB84 fast backend with intercept-resend, sifting, parameter estimation, theory and stats helpers. Write the tests listed in the M1 acceptance criteria. Run lint, mypy, pytest and fix everything. Summarize what you implemented, any decisions (also write them to docs/decisions.md), and the exact commands to verify.

**Prompt M2**
> Implement Milestone M2: the Qiskit BB84 backend using the stabilizer method with one multi-qubit circuit, plus noise-model support. Check the installed qiskit and qiskit-aer versions' APIs before coding. Add cross-backend statistical equivalence tests and a runtime-scaling note.

**Prompt M3**
> Implement Milestone M3: Cascade (with cascade-back), universal-hash verification, FFT Toeplitz privacy amplification, finite-key length calculation, FinalKey, and run_bb84_session. Meet the acceptance criteria including the n=1e6 performance target.

**Prompt M4–M5**
> Implement Milestones M4 and M5: monitoring layer (threshold, CI, SPRT, CUSUM, joint), policy engine, session state machine, JSONL events and evidence report, authenticated classical channel, and the classical MITM attack demo. Include Monte Carlo tests for false-alarm and detection rates.

**Prompt M6**
> Implement Milestone M6: HKDF key derivation, AES-256-GCM and ChaCha20-Poly1305 wrappers with strict nonce discipline, the chunked container format with AAD binding, key store. Add known-answer tests and negative/tamper tests.

**Prompt M7–M8**
> Implement Milestones M7 and M8: E91 (fast and Qiskit), CHSH computation with standard error, noise and Eve models, randomness tests, QRNG circuit, quantum-security table. Verify all numerical expectations and record discrepancies honestly.

**Prompt M9–M10**
> Implement all experiments E1–E15 with run_all, consistent plotting, CSV provenance, demos D1–D2, Vietnamese docs and references.bib. Do not fabricate results; generate everything from code. Provide a quick mode that finishes within 15 minutes.

---

## 22. Definition of done (whole project)

- All M0–M10 acceptance criteria pass in CI.
- `make setup test experiments` reproduces every figure/table from a clean clone.
- Report assets in Vietnamese, with limitations (Section 20) included.
- Every claim in docs is traceable to a CSV, a test, or a cited source.
- Stretch items are either implemented with tests or clearly listed as future work.
