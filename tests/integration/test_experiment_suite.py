"""Regression for deterministic E03 counts and the published artifact links."""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e03_artifacts(tmp_path: Path) -> None:
    """Check seeded counts, parse both figure formats, and resolve CSV provenance."""
    subprocess.run(
        [
            sys.executable,
            "experiments/run_all.py",
            "--quick",
            "--only",
            "3",
            "--output",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    data = tmp_path / "E03_sample_detection.csv"
    with data.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (Path(__file__).parent / "e03_quick_golden.csv").open(newline="") as stream:
        assert [(row["x"], row["successes"]) for row in rows] == [
            (row["x"], row["successes"]) for row in csv.DictReader(stream)
        ]
    meta = json.loads(data.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["csv_sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
    assert meta["seed"] and meta["git_commit"] and meta["library_versions"]
    assert data.with_suffix(".png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert data.with_suffix(".pdf").read_bytes().startswith(b"%PDF-")
