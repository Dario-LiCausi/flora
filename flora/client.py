"""Tiny Ollama client (standard library only). One request, no streaming, no tools, no proxy, no redirects."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .config import Config

MAX_REPLY = 4_000_000


class FloraError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # a redirect would send the prompt somewhere else


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
    # an empty ProxyHandler ignores HTTP(S)_PROXY in the environment: prompts and memory never go through a proxy
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    deadline = time.monotonic() + cfg.timeout
    try:
        with opener.open(req, timeout=cfg.timeout) as r:
            raw = b""
            while True:
                if time.monotonic() > deadline:
                    raise FloraError(f"model server too slow (over {cfg.timeout} s in total)")
                chunk = r.read(65536)
                if not chunk:
                    break
                raw += chunk
                if len(raw) > MAX_REPLY:
                    raise FloraError("model reply too large")
        data = json.loads(raw)
    except urllib.error.HTTPError as e:
        raise FloraError(f"model server answered HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FloraError(f"cannot reach the model server at {cfg.host}: {e}") from e
    except ValueError as e:
        raise FloraError("model server sent invalid JSON") from e
    text = data.get("response") if isinstance(data, dict) else None
    if not isinstance(text, str):
        raise FloraError("model server answer has no 'response' text")
    return text.strip()
