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
    def from_env() -> "Config":
        root = Path(__file__).resolve().parent.parent
        return Config(
            host=os.environ.get("FLORA_HOST", "http://127.0.0.1:11434"),
            model=os.environ.get("FLORA_MODEL", "flora"),
            memory_dir=Path(os.environ.get("FLORA_MEMORY_DIR", root / "memory")),
            max_memory_chars=int(os.environ.get("FLORA_MAX_MEMORY_CHARS", "8000")),
            timeout=int(os.environ.get("FLORA_TIMEOUT", "300")),
        )

    def check_local(self) -> None:
        """'No cloud by default': a non-loopback host needs an explicit opt-in."""
        host = urlparse(self.host).hostname or ""
        if host not in LOOPBACK and os.environ.get("FLORA_ALLOW_REMOTE") != "1":
            raise ValueError(f"refusing non-local host {host!r}; set FLORA_ALLOW_REMOTE=1 to allow it")
