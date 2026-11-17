"""Use UTF-8 for Vietnamese CLI output, including Windows pipes."""

import sys
from io import TextIOWrapper


def configure_utf8() -> None:
    """Keep redirected stdout and stderr consistent with UTF-8 artifact files."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
