"""Tiny Ollama client (standard library only). One request, no streaming, no tools."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import Config


class FloraError(Exception):
    pass


def generate(cfg: Config, prompt: str, temperature: float | None = None) -> str:
    cfg.check_local()
    body = {"model": cfg.model, "prompt": prompt, "stream": False}
    if temperature is not None:
        body["options"] = {"temperature": temperature}
    req = urllib.request.Request(
        cfg.host.rstrip("/") + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as r:
            data = json.loads(r.read(4_000_000))
    except urllib.error.HTTPError as e:
        raise FloraError(f"model server answered HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FloraError(f"cannot reach the model server at {cfg.host}: {e}") from e
    except ValueError as e:
        raise FloraError("model server sent invalid JSON") from e
    text = data.get("response")
    if not isinstance(text, str):
        raise FloraError("model server answer has no 'response' text")
    return text.strip()
