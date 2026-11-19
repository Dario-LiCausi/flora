"""Flora Bench: how dependable is a small local model on tiny text jobs? Same cases, same checks, several models.
Reports per model: pass rate (first try and with one retry), tokens per second, p95 latency, peak video memory (if nvidia-smi
exists), and WHY runs failed. Results are written as JSON so anyone can reproduce and compare."""
from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

from . import client, tasks
from .config import Config

CATEGORIES = ("format", "injection", "copied", "empty", "error")


def classify(problems: list[str], output: str) -> str:
    """One failure category for a failed run."""
    if not output.strip():
        return "empty"
    text = " ".join(problems).lower()
    if "forbidden" in text:
        return "injection"
    if "copies the style" in text:
        return "copied"
    return "format"


def check_case(case: dict, out: str) -> list[str]:
    """The case's own checks (shared with `flora eval`)."""
    from .cli import check_case as _check
    return _check(case, out)


def run_case(cfg: Config, case: dict) -> dict:
    """One attempt: build the prompt, ask the model, run the task check and the case checks."""
    text = case.get("text", "")
    t0 = time.monotonic()
    try:
        if case.get("task"):
            fields = case.get("fields")
            prompt = tasks.build_prompt(case["task"], text, fields)
            r = client.generate_stats(cfg, prompt, temperature=0.2)
            problems = tasks.validate(case["task"], text, r["text"], fields).problems + check_case(case, r["text"])
        else:
            r = client.generate_stats(cfg, case["prompt"], temperature=0.2)
            problems = check_case(case, r["text"])
    except (client.FloraError, ValueError) as e:
        return {"ok": False, "category": "error", "problems": [str(e)[:120]], "seconds": time.monotonic() - t0, "tokens": 0, "eval_s": 0}
    return {"ok": not problems, "category": None if not problems else classify(problems, r["text"]), "problems": problems,
            "seconds": time.monotonic() - t0, "tokens": r["tokens"], "eval_s": r["eval_s"]}


class VramSampler:
    """Peak used video memory (MiB) via nvidia-smi while a model runs. Silent no-op without nvidia-smi."""

    def __init__(self):
        self.peak = None
        self._stop = threading.Event()
        self._t = None

    def __enter__(self):
        if shutil.which("nvidia-smi"):
            self.peak = 0
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5, check=False).stdout.split()
                if out:
                    self.peak = max(self.peak, int(out[0]))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self._stop.wait(0.5)

    def __exit__(self, *a):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, round(0.95 * (len(v) - 1)))]


def bench_model(cfg: Config, model: str, cases: list[dict], repeats: int) -> dict:
    cfgm = replace(cfg, model=model)
    runs, retried_ok = [], 0
    with VramSampler() as vram:
        client.generate_stats(cfgm, "Say OK.")  # warm-up: load the model, not counted
        for case in cases:
            for _ in range(repeats):
                first = run_case(cfgm, case)
                runs.append(first)
                if not first["ok"] and first["category"] != "error":
                    retried_ok += int(run_case(cfgm, case)["ok"])  # one retry, only for answers that failed a check
    n = len(runs)
    ok = sum(r["ok"] for r in runs)
    tok, eval_s = sum(r["tokens"] for r in runs), sum(r["eval_s"] for r in runs)
    fails = {c: sum(1 for r in runs if r["category"] == c) for c in CATEGORIES}
    return {"model": model, "runs": n, "pass_first": ok, "pass_with_retry": ok + retried_ok,
            "pass_rate_first": round(ok / n, 3) if n else 0, "pass_rate_retry": round((ok + retried_ok) / n, 3) if n else 0,
            "tokens_per_s": round(tok / eval_s, 1) if eval_s else 0, "p95_s": round(p95([r["seconds"] for r in runs]), 2),
            "median_s": round(statistics.median([r["seconds"] for r in runs]), 2) if runs else 0,
            "peak_vram_mib": vram.peak, "failures": fails}


def table(results: list[dict]) -> str:
    head = "| Model | Pass (first try) | Pass (+1 retry) | Tokens/s | Median s | p95 s | Peak VRAM MiB | Failures (format/injection/copied/empty/error) |\n|---|---|---|---|---|---|---|---|\n"
    rows = []
    for r in results:
        f = r["failures"]
        rows.append(f"| {r['model']} | {r['pass_first']}/{r['runs']} ({r['pass_rate_first']:.0%}) | {r['pass_with_retry']}/{r['runs']} ({r['pass_rate_retry']:.0%}) | "
                    f"{r['tokens_per_s']} | {r['median_s']} | {r['p95_s']} | {r['peak_vram_mib'] if r['peak_vram_mib'] is not None else 'n/a'} | "
                    f"{f['format']}/{f['injection']}/{f['copied']}/{f['empty']}/{f['error']} |")
    return head + "\n".join(rows)


def run(cfg: Config, models: list[str], cases_file: Path, repeats: int, out: Path | None, label: str) -> str:
    from .memory import read_regular
    cases = json.loads(read_regular(cases_file, 1_000_000))
    results = [bench_model(cfg, m, cases, repeats) for m in models]
    doc = {"label": label, "date": time.strftime("%Y-%m-%d"), "repeats": repeats, "cases": len(cases), "results": results}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2) + "\n")
    return table(results)
