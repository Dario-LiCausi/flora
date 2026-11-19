"""Tests for Flora Bench. A stub server plays several models with different behaviour; no real model needed."""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flora import bench, cli
from flora.config import Config

CALLS = {}


class Models(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        model, n = body["model"], CALLS.get(body["model"], 0) + 1
        CALLS[model] = n
        if model == "down":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        text = {"good": "ok fine", "bad": "nope", "empty": "", "inject": "PWNED"}.get(model, "")
        if model == "flaky":  # warm-up call 1, first real call bad, then good
            text = "nope" if n == 2 else "ok fine"
        out = json.dumps({"response": text, "eval_count": 20, "eval_duration": 1_000_000_000, "total_duration": 1_500_000_000,
                          "load_duration": 100_000_000}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


CASE = {"name": "c", "prompt": "say ok", "checks": {"contains": ["ok"], "not_contains": ["pwned"]}}


class TestBench(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Models)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        CALLS.clear()
        for k in ("FLORA_TIMEOUT", "FLORA_ALLOW_REMOTE"):
            os.environ.pop(k, None)
        os.environ.update(FLORA_HOST=f"http://127.0.0.1:{self.srv.server_port}", FLORA_MODEL="x")
        self.cfg = Config.from_env()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_good_model_passes_and_speed_comes_from_the_server_numbers(self):
        r = bench.bench_model(self.cfg, "good", [CASE], 3)
        self.assertEqual((r["pass_first"], r["runs"], r["pass_rate_first"]), (3, 3, 1.0))
        self.assertEqual(r["tokens_per_s"], 20.0)
        self.assertEqual(sum(r["failures"].values()), 0)

    def test_failure_categories(self):
        self.assertEqual(bench.bench_model(self.cfg, "bad", [CASE], 2)["failures"]["format"], 2)
        self.assertEqual(bench.bench_model(self.cfg, "empty", [CASE], 2)["failures"]["empty"], 2)
        self.assertEqual(bench.bench_model(self.cfg, "inject", [CASE], 2)["failures"]["injection"], 2)

    def test_one_retry_rescues_a_flaky_model_but_is_counted_separately(self):
        r = bench.bench_model(self.cfg, "flaky", [CASE], 1)
        self.assertEqual((r["pass_first"], r["pass_with_retry"]), (0, 1))
        self.assertEqual(r["pass_rate_first"], 0.0)
        self.assertEqual(r["pass_rate_retry"], 1.0)

    def test_server_errors_are_their_own_category_and_not_retried(self):
        run = bench.run_case(Config.from_env().__class__(**{**self.cfg.__dict__, "model": "down"}), CASE)
        self.assertEqual(run["category"], "error")
        self.assertFalse(run["ok"])

    def test_classify_and_p95(self):
        self.assertEqual(bench.classify(["x"], ""), "empty")
        self.assertEqual(bench.classify(["contains forbidden 'x'"], "t"), "injection")
        self.assertEqual(bench.classify(['copies the style text: "a b"'], "t"), "copied")
        self.assertEqual(bench.classify(["3 bullets"], "t"), "format")
        self.assertEqual(bench.p95([]), 0.0)
        self.assertEqual(bench.p95([1, 2, 3, 4, 100]), 100)
        self.assertEqual(bench.p95([5]), 5)

    def test_vram_sampler_is_a_silent_noop_without_nvidia_smi(self):
        with mock.patch("flora.bench.shutil.which", return_value=None), bench.VramSampler() as v:
            pass
        self.assertIsNone(v.peak)

    def test_table_and_cli_write_json_and_print_a_table(self):
        cases = Path(self.tmp.name) / "cases.json"
        cases.write_text(json.dumps([CASE]))
        out = Path(self.tmp.name) / "res" / "r.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["bench", "--models", "good,bad", "--repeats", "2", "--cases", str(cases), "--out", str(out), "--label", "testbox"])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("| good |", text)
        self.assertIn("| bad |", text)
        doc = json.loads(out.read_text())
        self.assertEqual(doc["label"], "testbox")
        self.assertEqual([m["model"] for m in doc["results"]], ["good", "bad"])
        self.assertEqual(doc["results"][0]["pass_first"], 2)

    def test_cli_needs_models(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["bench", "--models", " , ", "--cases", "x"])
        self.assertEqual(rc, 2)

    def test_bad_cases_file_is_a_clean_error(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("not json")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["bench", "--models", "good", "--cases", str(bad)]), 2)


if __name__ == "__main__":
    unittest.main()
