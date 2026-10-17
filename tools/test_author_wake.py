#!/usr/bin/env python3
"""FLOW-56 for the reusable workflow's `notify` job, run, not read.

    python3 tools/test_author_wake.py        # what the `couplings` job runs

Contract FLOW-56: no plugins-service answer, refusal or outage may fail an
author's release run. `notify` in `.github/workflows/plugin-release.yml` makes
the one call ID-72 permits — ID-32's `author.wake` — and this file runs that
job's own `run:` block, cut out of the workflow as text, under bash as the
runner starts it (`bash --noprofile --norc -eo pipefail`), against a local
server standing in for both GitHub's OIDC token endpoint and the service.

Every case must exit 0. Beyond that, each one checks what the brief for the
job promised and what FLOW-55 and ID-32/ID-33 require:

* the body is exactly ID-32's bytes, the audience is exactly ID-32's, and the
  credential is the token just minted;
* the token is never printed except inside the `::add-mask::` command, and a
  refusal's `message` is never printed at all;
* at most one retry, only on a stated wait of at most 30 s, under a FRESH
  token — the service answers a reused `jti` with `replay` (ID-33);
* a 3xx is not followed, because urllib would carry the Authorization header
  to wherever it points;
* refusing, broken, redirecting, hanging and unreachable endpoints, a job
  without `id-token: write`, and a runner without python3 all end green.

The second class holds C25 (tools/check-registry-mirrors.py) to going red on
each break of the job's shape that FLOW-54/55/56 forbid, so that the static
rule and the behaviour cannot drift apart.

No network beyond 127.0.0.1, no token, no GitHub — which is why it runs in
`couplings`, on every pull request including a fork's. One case waits out the
script's 10-second request timeout on purpose.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

#: The fewest tests a run may report before it is a broken file rather than a
#: pass. The count of test methods below; raise it when you add one.
MIN_TESTS = 37


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIRRORS = _load("check_registry_mirrors", "check-registry-mirrors.py")
WORKFLOW = MIRRORS.PLUGIN_RELEASE.read_text(encoding="utf-8")
STEP = MIRRORS.step_block(MIRRORS.job_block(WORKFLOW, MIRRORS.NOTIFY_JOB), MIRRORS.WAKE_STEP)
RUN = MIRRORS.step_run(STEP)
ENV = MIRRORS.block_mapping(STEP, "env", 8) or {}

REQUEST_TOKEN = "request-token-from-the-runner"
RESULT = b'{"schema":"astra.plugins.author-wake-result/1"}'
#: Put in every refusal's `message`; the log must never carry it.
CANARY = "MESSAGE-TEXT-THE-LOG-MUST-NOT-CARRY"


def refusal(token: str, **extra) -> bytes:
    doc = {"schema": "astra.plugins.error/1", "error": token, "message": CANARY}
    doc.update(extra)
    return json.dumps(doc).encode()


class Mock:
    """GitHub's token endpoint at /token and the service at /wake.

    `answers` is what successive POSTs to /wake get, as
    (status, headers, body) or the string "hang"; the last one repeats.
    """

    def __init__(self) -> None:
        self.answers: list = [(200, {}, RESULT)]
        self.token_answer: tuple[int, bytes] | None = None
        self.minted: list[str] = []
        self.audiences: list[str] = []
        self.token_auth: list[str] = []
        self.posts: list[dict] = []
        self.other: list[tuple[str, dict]] = []
        self.release = threading.Event()
        mock_ = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the test transcript to results
                pass

            def _send(self, status, headers, body):
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path != "/token":
                    mock_.other.append((self.path, dict(self.headers)))
                    return self._send(404, {}, b"")
                mock_.token_auth.append(self.headers.get("Authorization", ""))
                mock_.audiences.extend(parse_qs(url.query).get("audience", []))
                if mock_.token_answer is not None:
                    status, body = mock_.token_answer
                    return self._send(status, {}, body)
                tok = f"eyJhbGciOiJSUzI1NiJ9.eyJqdGkiOiJ{len(mock_.minted)}fQ.c2lnbmF0dXJl{len(mock_.minted)}"
                mock_.minted.append(tok)
                self._send(200, {"Content-Type": "application/json"},
                           json.dumps({"count": 1, "value": tok}).encode())

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path != "/wake":
                    mock_.other.append((self.path, dict(self.headers)))
                    return self._send(404, {}, b"")
                mock_.posts.append({"body": body, "headers": dict(self.headers)})
                i = min(len(mock_.posts), len(mock_.answers)) - 1
                answer = mock_.answers[i]
                if answer == "hang":
                    mock_.release.wait(30)
                    return
                self._send(*answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WakeScriptBehaviour(unittest.TestCase):
    """The job's script, against every answer FLOW-56 says cannot fail a run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="author-wake-"))
        cls.script = cls.tmp / "run.sh"
        cls.script.write_text(RUN, encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self) -> None:
        self.mock = Mock()
        self.addCleanup(self.mock.close)

    def run_job(self, *, oidc: bool = True, wake_url: str | None = None,
                path: str | None = None) -> subprocess.CompletedProcess:
        env = {
            "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.tmp),
            "WAKE_URL": wake_url or self.mock.url("/wake"),
            "WAKE_AUDIENCE": ENV.get("WAKE_AUDIENCE", ""),
            # The runner's URL already carries a query; the script must append.
            "ACTIONS_ID_TOKEN_REQUEST_URL": self.mock.url("/token?api-version=2.0"),
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": REQUEST_TOKEN,
        }
        if not oidc:
            del env["ACTIONS_ID_TOKEN_REQUEST_URL"], env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
        bash = shutil.which("bash") or "/bin/bash"
        started = time.monotonic()
        p = subprocess.run([bash, "--noprofile", "--norc", "-eo", "pipefail", str(self.script)],
                           env=env, capture_output=True, text=True, timeout=90)
        self.elapsed = time.monotonic() - started
        self.log = p.stdout + p.stderr
        return p

    def assert_green(self, p: subprocess.CompletedProcess) -> None:
        self.assertEqual(p.returncode, 0, f"the job's script exited {p.returncode}:\n{self.log}")
        self.assertNotIn(CANARY, self.log, "a refusal's message reached the log")
        self.assertNotIn(REQUEST_TOKEN, self.log, "the runner's request token reached the log")
        for tok in self.mock.minted:
            for line in self.log.splitlines():
                if tok in line:
                    self.assertEqual(line, f"::add-mask::{tok}",
                                     f"the OIDC token was printed outside its mask command:\n{line}")
        for post in self.mock.posts:
            self.assertEqual(post["body"], MIRRORS.WAKE_BODY.encode(), "the body is not ID-32's")
            self.assertEqual(post["headers"].get("Content-Type"), "application/json")
            auth = post["headers"].get("Authorization", "")
            self.assertTrue(auth.startswith("Bearer ") and auth[7:] in self.mock.minted,
                            "the credential is not a token this job minted")
        self.assertTrue(all(a == f"Bearer {REQUEST_TOKEN}" for a in self.mock.token_auth))
        self.assertTrue(all(a == MIRRORS.WAKE_AUDIENCE for a in self.mock.audiences),
                        f"minted for {self.mock.audiences}, not ID-32's audience")
        self.assertFalse(self.mock.other, f"requests to anything but /token and /wake: {self.mock.other}")

    # ── what the workflow compiles in ────────────────────────────────────────

    def test_the_script_was_found(self) -> None:
        self.assertGreaterEqual(len(RUN.splitlines()), MIRRORS.FLOOR_WAKE_RUN_LINES, RUN[:400])
        self.assertEqual(ENV.get("WAKE_URL"), MIRRORS.WAKE_URL)
        self.assertEqual(ENV.get("WAKE_AUDIENCE"), MIRRORS.WAKE_AUDIENCE)

    # ── answers ──────────────────────────────────────────────────────────────

    def test_accepted(self) -> None:
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 1)
        self.assertEqual(len(self.mock.minted), 1)
        self.assertIn("HTTP 200, astra.plugins.author-wake-result/1", self.log)
        self.assertIn(f"::add-mask::{self.mock.minted[0]}", self.log)

    def test_success_status_with_another_body(self) -> None:
        self.mock.answers = [(200, {}, b'{"schema":"something-else/1","secret":"x"}')]
        p = self.run_job()
        self.assert_green(p)
        self.assertIn("HTTP 200, but not astra.plugins.author-wake-result/1", self.log)
        self.assertNotIn("something-else", self.log)

    def _refused_once(self, token: str, status: int) -> None:
        self.mock.answers = [(status, {"Content-Type": "application/json"}, refusal(token))]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 1, "a refusal with no stated wait was retried")
        self.assertIn(f"HTTP {status}, refused: {token}", self.log)

    def test_token_refused(self) -> None:
        self._refused_once("token_refused", 422)

    def test_replay(self) -> None:
        self._refused_once("replay", 409)

    def test_invalid(self) -> None:
        self._refused_once("invalid", 422)

    def test_unavailable_without_a_stated_wait(self) -> None:
        self._refused_once("unavailable", 503)

    def test_rate_limited_without_a_stated_wait(self) -> None:
        self._refused_once("rate_limited", 429)

    def test_unknown_token_is_not_echoed(self) -> None:
        self.mock.answers = [(422, {}, refusal("brand_new_token_x"))]
        p = self.run_job()
        self.assert_green(p)
        self.assertNotIn("brand_new_token_x", self.log)
        self.assertIn("a token this workflow does not know", self.log)

    # ── the one retry ────────────────────────────────────────────────────────

    def test_rate_limited_short_wait_retries_once_under_a_fresh_token(self) -> None:
        self.mock.answers = [(429, {}, refusal("rate_limited", retry_after=1)), (200, {}, RESULT)]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 2)
        self.assertEqual(len(self.mock.minted), 2)
        used = [x["headers"]["Authorization"] for x in self.mock.posts]
        self.assertNotEqual(used[0], used[1], "the retry reused a token the service may have seen (ID-33)")
        self.assertIn("waiting the stated 1 s", self.log)
        self.assertIn("HTTP 200, astra.plugins.author-wake-result/1", self.log)

    def test_unavailable_with_retry_after_header_retries_at_most_once(self) -> None:
        self.mock.answers = [(503, {"Retry-After": "1"}, refusal("unavailable"))]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 2, "a second stated wait must end the job's calls")

    def test_503_without_a_body_but_a_short_retry_after_retries(self) -> None:
        self.mock.answers = [(503, {"Retry-After": "0"}, b"<html>bad gateway</html>"), (200, {}, RESULT)]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 2)
        self.assertIn("HTTP 503, with no refusal body", self.log)
        self.assertNotIn("bad gateway", self.log)

    def test_a_long_stated_wait_is_not_waited(self) -> None:
        self.mock.answers = [(429, {"Retry-After": "31"}, refusal("rate_limited", retry_after=31))]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 1)
        self.assertLess(self.elapsed, 20)

    def test_an_http_date_retry_after_is_no_stated_wait(self) -> None:
        self.mock.answers = [(503, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, b"")]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 1)

    def test_a_refusal_that_is_not_busy_is_not_retried_whatever_it_states(self) -> None:
        self.mock.answers = [(422, {"Retry-After": "1"}, refusal("token_refused", retry_after=1))]
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(len(self.mock.posts), 1)

    # ── broken and missing endpoints ─────────────────────────────────────────

    def test_server_error_with_html(self) -> None:
        self.mock.answers = [(500, {"Content-Type": "text/html"}, b"<h1>oops</h1>")]
        p = self.run_job()
        self.assert_green(p)
        self.assertIn("HTTP 500, with no refusal body", self.log)

    def _not_followed(self, status: int) -> None:
        self.mock.answers = [(status, {"Location": self.mock.url("/steal")}, b"")]
        p = self.run_job()
        self.assertEqual(p.returncode, 0, self.log)
        self.assertEqual(self.mock.other, [], f"the token followed a {status}")
        self.assertEqual(len(self.mock.posts), 1)

    # urllib's default handler follows a 302 or 303 after a POST as a GET, and
    # re-sends every header with it — Authorization included, to any host.
    def test_a_302_is_not_followed(self) -> None:
        self._not_followed(302)

    def test_a_307_is_not_followed(self) -> None:
        self._not_followed(307)

    def test_unreachable(self) -> None:
        p = self.run_job(wake_url=f"http://127.0.0.1:{closed_port()}/wake")
        self.assert_green(p)
        self.assertIn("no answer (URLError)", self.log)

    def test_a_server_that_never_answers(self) -> None:
        self.mock.answers = ["hang"]
        p = self.run_job()
        self.assert_green(p)
        self.assertIn("no answer (", self.log)
        self.assertLess(self.elapsed, 40)

    def test_no_id_token_permission(self) -> None:
        p = self.run_job(oidc=False)
        self.assert_green(p)
        self.assertEqual(self.mock.posts, [])
        self.assertIn("cannot mint an OIDC token", self.log)

    def test_github_refuses_the_token_request(self) -> None:
        self.mock.token_answer = (403, b'{"message":"no"}')
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(self.mock.posts, [])
        self.assertIn("GitHub refused the OIDC token request (HTTP 403)", self.log)

    def test_a_token_answer_that_would_inject_a_workflow_command(self) -> None:
        self.mock.token_answer = (200, json.dumps({"value": "a.b.c\n::set-env name=X::y"}).encode())
        p = self.run_job()
        self.assert_green(p)
        self.assertEqual(self.mock.posts, [])
        self.assertNotIn("::set-env", self.log)
        self.assertNotIn("::add-mask::", self.log)

    def test_no_python_on_the_runner(self) -> None:
        empty = self.tmp / "empty-bin"
        empty.mkdir(exist_ok=True)
        p = self.run_job(path=str(empty))
        self.assertEqual(p.returncode, 0, self.log)
        self.assertEqual(self.mock.posts, [])


class C25IsRedOnEachBreak(unittest.TestCase):
    """The static half: each shape FLOW-54/55/56 forbid turns C25 red."""

    def c25(self, workflow: str, caller: str | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plugin-release.yml"
            path.write_text(workflow, encoding="utf-8")
            fails = MIRRORS.Fails()
            patches = [mock.patch.object(MIRRORS, "PLUGIN_RELEASE", path),
                       mock.patch.object(MIRRORS, "ROOT", Path(d))]
            if caller is not None:
                patches.append(mock.patch.object(MIRRORS, "generated_caller", lambda: caller))
            with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()):
                for p in patches:
                    stack.enter_context(p)
                stack.enter_context(mock.patch.object(MIRRORS, "INIT_CI", Path(d) / "init_ci.rs"))
                if caller is None:
                    stack.enter_context(mock.patch.object(MIRRORS, "generated_caller", lambda: ""))
                MIRRORS.rule_C25(fails)
            return list(fails)

    def broken(self, old: str, new: str, *, count: int = 1) -> str:
        self.assertEqual(WORKFLOW.count(old), count, f"the mutation's anchor moved: {old!r}")
        return WORKFLOW.replace(old, new)

    def assert_red(self, workflow: str, expect: str, caller: str | None = None) -> None:
        fails = self.c25(workflow, caller)
        self.assertTrue(any(expect in f for f in fails), f"C25 stayed green on the break; fails: {fails}")

    def test_green_on_this_tree(self) -> None:
        self.assertEqual(self.c25(WORKFLOW), [])

    def test_a_second_permission(self) -> None:
        self.assert_red(self.broken("      id-token: write   # mint the author OIDC token",
                                    "      contents: read\n      id-token: write   # mint the author OIDC token"),
                        "holds only `id-token: write`")

    def test_a_checkout(self) -> None:
        self.assert_red(self.broken("    steps:\n      # Python's stdlib",
                                    "    steps:\n      - uses: actions/checkout@v4\n      # Python's stdlib"),
                        "holds only `id-token: write`")

    def test_the_job_can_fail(self) -> None:
        self.assert_red(self.broken("    timeout-minutes: 3\n    continue-on-error: true\n",
                                    "    timeout-minutes: 3\n"),
                        "holds only `id-token: write`")

    def test_the_step_can_fail(self) -> None:
        self.assert_red(self.broken("        id: wake\n        continue-on-error: true\n",
                                    "        id: wake\n"),
                        "sends ID-32's `author.wake` exactly")

    def test_the_shell_line_can_fail(self) -> None:
        self.assert_red(self.broken("python3 - <<'PY' || true", "python3 - <<'PY'"),
                        "sends ID-32's `author.wake` exactly")

    def test_another_body(self) -> None:
        self.assert_red(self.broken(MIRRORS.WAKE_BODY,
                                    '{"schema":"astra.plugins.author-wake/1","tag":"v1"}'),
                        "sends ID-32's `author.wake` exactly")

    def test_another_audience(self) -> None:
        self.assert_red(self.broken(f"WAKE_AUDIENCE: {MIRRORS.WAKE_AUDIENCE}",
                                    "WAKE_AUDIENCE: https://api.minice.ai/plugins/v1"),
                        "sends ID-32's `author.wake` exactly")

    def test_no_fork_clause(self) -> None:
        self.assert_red(self.broken("      && github.event.repository.fork != true\n", ""),
                        "holds only `id-token: write`")

    def test_build_gains_id_token(self) -> None:
        self.assert_red(self.broken("these two lines.\n      contents: read\n",
                                    "these two lines.\n      contents: read\n      id-token: write\n"),
                        "can mint an OIDC token")

    def test_a_fifth_job(self) -> None:
        self.assert_red(WORKFLOW + "\n  extra:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: true\n",
                        "jobs are exactly")

    def test_the_service_named_outside_notify(self) -> None:
        self.assert_red(self.broken("          echo \"Published $TAG\"\n",
                                    "          echo \"Published $TAG\"\n          python3 -c 'import urllib.request'\n"),
                        "only `notify` names the plugins service")

    def test_the_generated_caller_names_the_service(self) -> None:
        self.assert_red(WORKFLOW, "only `notify` names the plugins service",
                        caller=f"# audience {MIRRORS.WAKE_AUDIENCE}\n")


if __name__ == "__main__":
    prog = unittest.main(exit=False, verbosity=2)
    ran = prog.result.testsRun
    if ran < MIN_TESTS:
        print(f"test_author_wake: {ran} test(s) ran, want >= {MIN_TESTS}. A test file that "
              "stopped collecting its tests is not a pass.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0 if prog.result.wasSuccessful() else 1)
