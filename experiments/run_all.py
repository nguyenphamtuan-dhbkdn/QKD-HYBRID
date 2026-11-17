"""Generate E1–E15 CSV, JSON provenance, PNG, PDF and report includes."""

import argparse
import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml
from _crypto_trials import e09, e10, e11, e12
from _diagnostics import e13, e14, e15
from _protocols import e01, e02, e03, e04, e05, e06, e07, e08
from _provenance import ROOT, provenance
from _report import interpretation, result_table
from _suite import Experiment
from plotting import FIGURES, plot

from qkdsim.config import SessionConfig, load_config

EXPERIMENTS: tuple[Callable[[Experiment], None], ...] = (
    e01,
    e02,
    e03,
    e04,
    e05,
    e06,
    e07,
    e08,
    e09,
    e10,
    e11,
    e12,
    e13,
    e14,
    e15,
)
LIBRARIES = (
    "numpy",
    "scipy",
    "matplotlib",
    "PyYAML",
    "qiskit",
    "qiskit-aer",
    "cryptography",
)


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Store strict JSON alongside data files."""
    path.write_text(
        json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_suite(
    config_path: Path,
    output: Path,
    *,
    quick: bool,
    language: str | None,
    selection: list[int] | None,
) -> None:
    """Recreate artifacts, then record aggregate runtime and report includes."""
    started = perf_counter()
    raw_config = config_path.read_bytes()
    config = yaml.safe_load(raw_config)
    lang = language or config["language"]
    if lang not in ("vi", "en"):
        raise ValueError("language must be vi or en")
    output.mkdir(parents=True, exist_ok=True)
    source = provenance(*LIBRARIES)
    includes = ["# Kết quả thực nghiệm", ""]
    runs = {}
    for number in sorted(set(selection or range(1, len(EXPERIMENTS) + 1))):
        start = perf_counter()
        name = f"E{number:02}"
        figure = FIGURES[number - 1]
        stem = f"{name}_{figure.slug}"
        entry = config["experiments"][name]
        option_path = config_path.parent / entry if isinstance(entry, str) else None
        raw_options = option_path.read_bytes() if option_path is not None else None
        options = yaml.safe_load(raw_options) if raw_options is not None else entry
        exp = Experiment(number, config["seed"], quick, options)
        EXPERIMENTS[number - 1](exp)
        if not exp.rows:
            raise ValueError(
                f"{name} produced no rows; check the experiment configuration"
            )
        data = output / f"{stem}.csv"
        columns = list(dict.fromkeys(key for row in exp.rows for key in row))
        with data.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(exp.rows)
        plot(data, figure, lang)
        seconds = perf_counter() - start
        auxiliary = (
            asdict(load_config(ROOT / "configs" / options["session"]))
            if "session" in options
            else None
        )
        write_json(
            data.with_suffix(".json"),
            {
                **source,
                "experiment": name,
                "seed": exp.seed,
                "rng": "SeedSequence(seed, spawn_key=(experiment_number, trial_index))",
                "quick": quick,
                "language": lang,
                "config": options,
                "options_sha256": (
                    hashlib.sha256(raw_options).hexdigest() if raw_options else None
                ),
                "config_sha256": hashlib.sha256(raw_config).hexdigest(),
                "session_defaults": asdict(SessionConfig()),
                "auxiliary_session": auxiliary,
                "os_entropy": "AEAD, session IDs, verification, PA, fixtures",
                "csv": data.name,
                "csv_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
                "figures": [f"{stem}.png", f"{stem}.pdf"],
                "rows": len(exp.rows),
                "seconds": seconds,
            },
        )
        includes.extend(
            [
                f"## {name} — {figure.title[0]}",
                "",
                interpretation(exp),
                "",
                *result_table(exp),
                f"![{figure.title[0]}]({stem}.png)",
                "",
                f"[CSV]({data.name}) · [PDF]({stem}.pdf) · [Nguồn gốc]({stem}.json)",
                "",
            ]
        )
        runs[name] = {"rows": len(exp.rows), "seconds": seconds}
        print(f"{name} {len(exp.rows)} rows in {seconds:.2f} s", flush=True)

    report = "report_results.md" if selection is None else "report_selected.md"
    manifest = "run_all.json" if selection is None else "run_selected.json"
    (output / report).write_text("\n".join(includes), encoding="utf-8")
    outline = ROOT / "docs" / "report_outline_vi.md"
    full_report = None
    if selection is None and outline.is_file():
        full_report = "report_vi.md"
        section = "\n".join(
            "#" + line if line.startswith("## ") else line for line in includes[2:]
        )
        (output / full_report).write_text(
            outline.read_text(encoding="utf-8").replace(
                "<!-- experiment-results -->", section
            ),
            encoding="utf-8",
        )
    seconds = perf_counter() - started
    write_json(
        output / manifest,
        {
            **source,
            "seed": config["seed"],
            "quick": quick,
            "language": lang,
            "seconds": seconds,
            "experiments": runs,
            "report": report,
            "full_report": full_report,
        },
    )
    print(f"Total {seconds:.2f} s in {output}", flush=True)


def main() -> None:
    """Run the full profile unless explicitly given --quick."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--language", choices=["vi", "en"])
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "experiments.yaml"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--only", nargs="+", type=int, choices=range(1, 16), metavar="N"
    )
    args = parser.parse_args()
    profile = "quick" if args.quick else "full"
    results = ROOT / "results"
    if args.only is not None:
        results /= "selected"
    output = args.output or results / profile
    run_suite(
        args.config,
        output,
        quick=args.quick,
        language=args.language,
        selection=args.only,
    )


if __name__ == "__main__":
    main()
