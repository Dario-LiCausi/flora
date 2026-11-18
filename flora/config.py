"""Settings come from environment variables only (no hidden config files)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Config:
    host: str
    model: str
    memory_dir: Path
    max_memory_chars: int
    timeout: int

    @staticmethod
    def from_env() -> Config:
        root = Path(__file__).resolve().parent.parent

        def num(name: str, default: str, low: int, high: int) -> int:
            try:
                v = int(os.environ.get(name, default))
            except ValueError:
                raise ValueError(f"{name} must be a whole number") from None
            if not low <= v <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
            return v

        return Config(
            host=os.environ.get("FLORA_HOST", "http://127.0.0.1:11434"),
            model=os.environ.get("FLORA_MODEL", "flora"),
            memory_dir=Path(os.environ.get("FLORA_MEMORY_DIR", root / "memory")),
            max_memory_chars=num("FLORA_MAX_MEMORY_CHARS", "8000", 100, 200_000),
            timeout=num("FLORA_TIMEOUT", "300", 1, 3600),
        )

    def check_local(self) -> None:
        """'No cloud by default': a non-loopback host needs an explicit opt-in."""
        host = urlparse(self.host).hostname or ""
        if host not in LOOPBACK and os.environ.get("FLORA_ALLOW_REMOTE") != "1":
            raise ValueError(f"refusing non-local host {host!r}; set FLORA_ALLOW_REMOTE=1 to allow it")
