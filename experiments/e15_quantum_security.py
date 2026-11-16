"""Generate the E15 model-based quantum security table and its provenance."""

import csv
import json
from dataclasses import asdict, fields

from _provenance import ROOT, provenance

from qkdsim.analysis.quantum_security import SecurityRow, security_rows


def main() -> None:
    """Write values computed from E15 key sizes and the NIST strength classes."""
    rows = security_rows()
    output = ROOT / "results" / "e15_quantum_security.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=[field.name for field in fields(SecurityRow)]
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    metadata = {
        **provenance("numpy", "scipy"),
        "config": {
            "primitives_and_key_sizes": {row.primitive: row.key_bits for row in rows}
        },
        "seed": None,
        "classical_asymmetric_strength_source": "NIST SP 800-57 Part 1 Rev. 5 Table 2",
    }
    output.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
