"""File-based memory. Read-only at run time. Changes happen only through proposals that a human approves."""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path

CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
TARGET_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MAX_TEXT = 500
MAX_FILE = 64 * 1024          # one memory or proposal file
MAX_PROPOSALS = 500


class MemoryError_(Exception):
    pass


def clean(text: str, limit: int = MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", CTRL.sub(" ", text)).strip()[:limit]


def read_regular(path: Path, limit: int = MAX_FILE) -> str:
    """Read at most `limit` bytes of a REGULAR file, never following a symlink and never blocking on a pipe."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise MemoryError_(f"{path.name} is not a regular file")
        return f.read(limit + 1)[:limit].decode("utf-8", "replace")


def load(memory_dir: Path, max_chars: int) -> str:
    """All *.md memory files as labelled DATA, capped. Missing folder = no memory."""
    out = ""
    if memory_dir.is_dir():
        for f in sorted(memory_dir.glob("*.md")):
            try:
                out += f"[MEMORY FILE: {f.name}]\n{read_regular(f)}\n\n"
            except (OSError, MemoryError_):
                continue  # symlinks, pipes and unreadable files are skipped, not followed
            if len(out) > max_chars:
                break
    if len(out) > max_chars:
        out = out[:max_chars] + "\n[MEMORY TRUNCATED]\n\n"
    return out


def _dir(memory_dir: Path, *parts: str) -> Path:
    """A real directory inside the memory folder (a symlink there is refused)."""
    d = memory_dir.joinpath(*parts)
    if d.is_symlink() or (d.exists() and not d.is_dir()):
        raise MemoryError_(f"{d.name} must be a real folder, not a link")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append(path: Path, line: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line)


def _audit(memory_dir: Path, action: str, pid: str, target: str = "") -> None:
    """Append-only log. It records WHAT happened, never the memory text."""
    _dir(memory_dir)
    _append(memory_dir / "audit.log", json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "id": pid, "target": target}) + "\n")


def _valid(rec: object, pid: str) -> dict:
    """A proposal record is trusted only if every field is well formed and matches its file name."""
    if (not isinstance(rec, dict) or rec.get("id") != pid or rec.get("status") != "pending"
            or not isinstance(rec.get("target"), str) or not TARGET_RE.fullmatch(rec["target"])
            or not isinstance(rec.get("text"), str)):
        raise MemoryError_("proposal record is invalid")
    return {"id": pid, "target": rec["target"], "text": clean(rec["text"]), "status": "pending"}


def propose(memory_dir: Path, target: str, text: str) -> str:
    if not TARGET_RE.fullmatch(target):
        raise MemoryError_("target must be 1-40 chars of a-z, 0-9, _ or -")
    text = clean(text)
    if not text:
        raise MemoryError_("empty proposal")
    d = _dir(memory_dir, "proposals")
    if len(list(d.glob("*.json"))) >= MAX_PROPOSALS:
        raise MemoryError_("too many pending proposals; approve or reject some first")
    pid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    fd = os.open(d / f"{pid}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"id": pid, "target": target, "text": text, "status": "pending"}))
    _audit(memory_dir, "propose", pid, target)
    return pid


def get(memory_dir: Path, pid: str) -> dict:
    """The validated pending proposal (what the operator should be shown before approving)."""
    if not ID_RE.fullmatch(pid):
        raise MemoryError_("bad proposal id")
    p = memory_dir / "proposals" / f"{pid}.json"
    try:
        return _valid(json.loads(read_regular(p)), pid)
    except (OSError, ValueError):
        raise MemoryError_("no such pending proposal") from None


def list_pending(memory_dir: Path) -> list[dict]:
    d = memory_dir / "proposals"
    out = []
    if d.is_dir() and not d.is_symlink():
        for p in sorted(d.glob("*.json"))[:MAX_PROPOSALS]:
            try:
                out.append(get(memory_dir, p.stem))
            except MemoryError_:
                continue  # links, odd files and tampered records are not listed
    return out


class _Lock:
    def __enter__(self):
        return self

    def __init__(self, memory_dir: Path):
        _dir(memory_dir)
        self.f = open(memory_dir / ".lock", "a")  # noqa: SIM115  (held until __exit__)
        fcntl.flock(self.f, fcntl.LOCK_EX)

    def __exit__(self, *a):
        self.f.close()


def _claim(memory_dir: Path, pid: str) -> Path:
    """Atomically take the pending file. Only ONE caller wins; a second approve gets 'already handled'."""
    src = memory_dir / "proposals" / f"{pid}.json"
    mine = memory_dir / "proposals" / f".claim-{pid}"
    try:
        os.rename(src, mine)
    except OSError:
        raise MemoryError_("no such pending proposal (already handled?)") from None
    return mine


def _archive(memory_dir: Path, claimed: Path, rec: dict, status: str) -> None:
    done = _dir(memory_dir, "proposals", "done")
    fd = os.open(done / f"{rec['id']}.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({**rec, "status": status}))
    claimed.unlink()


def approve(memory_dir: Path, pid: str) -> str:
    """The ONLY function that writes to memory files. Appends one clean line, once, and logs it."""
    with _Lock(memory_dir):
        rec = get(memory_dir, pid)
        target_file = memory_dir / f"{rec['target']}.md"
        if memory_dir.resolve() not in target_file.resolve().parents:
            raise MemoryError_("target outside the memory folder")
        claimed = _claim(memory_dir, pid)
        try:
            _append(target_file, f"- {rec['text']} (added {time.strftime('%Y-%m-%d')}, proposal {pid})\n")
        except OSError as e:
            os.rename(claimed, memory_dir / "proposals" / f"{pid}.json")  # put it back: nothing was approved
            raise MemoryError_(f"could not write memory: {e.strerror}") from None
        _archive(memory_dir, claimed, rec, "approved")
        _audit(memory_dir, "approve", pid, rec["target"])
        return rec["target"]


def reject(memory_dir: Path, pid: str) -> None:
    with _Lock(memory_dir):
        rec = get(memory_dir, pid)
        claimed = _claim(memory_dir, pid)
        _archive(memory_dir, claimed, rec, "rejected")
        _audit(memory_dir, "reject", pid, rec["target"])
