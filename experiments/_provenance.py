"""Report the local source revision and runtime for an experiment."""

import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def provenance(*libraries: str) -> dict[str, object]:
    """Record the base commit, working-tree state, and actual library versions."""
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
        "python": platform.python_version(),
        "library_versions": {name: version(name) for name in libraries},
    }
