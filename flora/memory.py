"""File-based memory. Read-only at run time. Changes happen only through proposals that a human approves."""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f  ​-‏‪-‮⁦-⁩]")
ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
TARGET_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MAX_TEXT = 500


class MemoryError_(Exception):
    pass


def clean(text: str, limit: int = MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", CTRL.sub(" ", text)).strip()[:limit]


def load(memory_dir: Path, max_chars: int) -> str:
    """All *.md memory files as labelled DATA, capped. Missing folder = no memory."""
    out = ""
    if memory_dir.is_dir():
        for f in sorted(memory_dir.glob("*.md")):
            if f.is_file() and not f.is_symlink():
                out += f"[MEMORY FILE: {f.name}]\n{f.read_text(errors='replace')}\n\n"
    if len(out) > max_chars:
        out = out[:max_chars] + "\n[MEMORY TRUNCATED]\n\n"
    return out


def _proposals(memory_dir: Path) -> Path:
    return memory_dir / "proposals"


def _audit(memory_dir: Path, action: str, pid: str, target: str = "") -> None:
    """Append-only log. It records WHAT happened, never the memory text."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    with open(memory_dir / "audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "id": pid, "target": target}) + "\n")


def propose(memory_dir: Path, target: str, text: str) -> str:
    if not TARGET_RE.fullmatch(target):
        raise MemoryError_("target must be 1-40 chars of a-z, 0-9, _ or -")
    text = clean(text)
    if not text:
        raise MemoryError_("empty proposal")
    pid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    d = _proposals(memory_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps({"id": pid, "target": target, "text": text, "status": "pending"}))
    _audit(memory_dir, "propose", pid, target)
    return pid


def _read(memory_dir: Path, pid: str) -> dict:
    if not ID_RE.fullmatch(pid):
        raise MemoryError_("bad proposal id")
    p = _proposals(memory_dir) / f"{pid}.json"
    if not p.is_file() or p.is_symlink():
        raise MemoryError_("no such pending proposal")
    return json.loads(p.read_text())


def list_pending(memory_dir: Path) -> list[dict]:
    d = _proposals(memory_dir)
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text()))
            except ValueError:
                continue
    return out


def _finish(memory_dir: Path, pid: str, status: str) -> None:
    d = _proposals(memory_dir)
    (d / "done").mkdir(exist_ok=True)
    src = d / f"{pid}.json"
    data = json.loads(src.read_text())
    data["status"] = status
    (d / "done" / f"{pid}.json").write_text(json.dumps(data))
    src.unlink()


def approve(memory_dir: Path, pid: str) -> str:
    """The ONLY function that writes to memory files. Appends one bullet and logs it."""
    prop = _read(memory_dir, pid)
    target_file = memory_dir / f"{prop['target']}.md"
    if memory_dir.resolve() not in target_file.resolve().parents:
        raise MemoryError_("target outside the memory folder")
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(f"- {prop['text']} (added {time.strftime('%Y-%m-%d')}, proposal {pid})\n")
    _finish(memory_dir, pid, "approved")
    _audit(memory_dir, "approve", pid, prop["target"])
    return prop["target"]


def reject(memory_dir: Path, pid: str) -> None:
    prop = _read(memory_dir, pid)
    _finish(memory_dir, pid, "rejected")
    _audit(memory_dir, "reject", pid, prop["target"])
