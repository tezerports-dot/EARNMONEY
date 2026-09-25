"""Reset and seed the security-probe database (see security/run.sh).

Reuses e2e/stack.py, but the target database ends in _sec.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "e2e"))

import stack  # noqa: E402


def _check() -> str:
    from urllib.parse import urlparse

    url = os.environ["FF_DATABASE_URL"]
    name = urlparse(url.replace("+asyncpg", "")).path.lstrip("/")
    if not name.endswith("_sec"):
        sys.exit(f"Refusing to use database {name!r}: security runs need a database ending in _sec.")
    return url


if __name__ == "__main__":
    import asyncio

    url = _check()
    if sys.argv[1] == "reset":
        stack.reset(url)
    elif sys.argv[1] == "setup":
        asyncio.run(stack.setup())
