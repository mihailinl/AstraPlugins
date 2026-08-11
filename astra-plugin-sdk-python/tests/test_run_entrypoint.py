"""`Plugin.run()` in a real subprocess — the entry point every plugin uses.

Everything else in this suite drives `_run_async`. `run()` itself — argv
parsing, the reserved-name assertion, the asyncio bootstrap — is what the daemon
actually invokes, and it had no coverage at all. A failure here is a plugin that
never starts, which is the failure mode with the least diagnostic information
attached to it.
"""

import asyncio
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from astra_plugin_sdk.limits import PLUGIN_START_TIMEOUT_SECS
from astra_plugin_sdk.testing import MockDaemon

PLUGIN_SOURCE = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {sdk_path!r})
    from astra_plugin_sdk import Plugin, tool

    class Spawned(Plugin):
        @tool("Say hello")
        async def hello(self, name: str = "world"):
            return {{"greeting": "hello " + name}}

    Spawned().run()
    """
)


class _DaemonThread:
    """A `MockDaemon` on its own loop, reachable from a child process."""

    def __init__(self, daemon: MockDaemon):
        self.daemon = daemon
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(daemon.start(), self._loop).result(10)

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.daemon.stop(), self._loop).result(10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
        self._loop.close()


def _spawn(daemon: MockDaemon, *extra_argv: str) -> subprocess.Popen:
    sdk_path = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    # PYTHONUNBUFFERED is stripped on purpose. The daemon sets it for plugins
    # whose manifest names the `python` runtime, but it cannot for one launched
    # through a wrapper, a shell, or a frozen binary — and a test that inherits
    # it from whoever ran pytest is a test that can never see the buffering bug
    # this file exists to catch.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            PLUGIN_SOURCE.format(sdk_path=sdk_path),
            "--daemon-addr",
            daemon.address,
            "--plugin-id",
            "spawned",
            "--auth-token",
            daemon.auth_token,
            *extra_argv,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _first_line(process, timeout: float) -> str | None:
    """The child's first line of stdout, or `None` if it never arrived in time.

    Read on a thread with a deadline, and read *while the process is still
    running*. That is the whole point: `communicate()` after `terminate()`
    returns everything the child ever wrote, including whatever was sitting in
    a block buffer until the interpreter flushed it on the way out — so an
    assertion on that output passes just as happily for a plugin whose first
    line reached the daemon in a millisecond and for one whose first line
    reached it never.
    """
    box: queue.Queue = queue.Queue(maxsize=1)

    def reader():
        try:
            box.put(process.stdout.readline())
        except Exception:  # noqa: BLE001 — the pipe closed under us
            box.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        line = box.get(timeout=timeout)
    except queue.Empty:
        return None
    return line.rstrip("\n") if line else None


def _wait_for_registration(daemon: MockDaemon, process, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if daemon.registrations:
            return daemon.registrations[0]
        if process.poll() is not None:
            out, err = process.communicate()
            pytest.fail(f"the plugin exited with {process.returncode}\n{out}\n{err}")
        time.sleep(0.05)
    pytest.fail("the plugin never registered")


@pytest.fixture
def daemon():
    thread = _DaemonThread(MockDaemon(config={"greeting": "hi"}, language="uk"))
    try:
        yield thread.daemon
    finally:
        thread.stop()


def test_run_starts_registers_and_shuts_down(daemon):
    process = _spawn(daemon)
    try:
        # The readiness signal FIRST, and while the process is still alive.
        #
        # `PendingSpawn::run` waits for the child's first line of output and
        # gives it `PLUGIN_START_TIMEOUT` to produce one; past that it kills the
        # process group and classifies the failure `start_timeout`
        # (astra-daemon/src/plugins/instance.rs). Python block-buffers stdout
        # when it is a pipe, so without `sys.stdout.reconfigure(line_buffering=
        # True)` and `flush=True` on the startup prints, this line does not
        # appear until the interpreter exits — the plugin registers, answers
        # every hook, and is killed anyway.
        line = _first_line(process, timeout=PLUGIN_START_TIMEOUT_SECS)
        assert line is not None, (
            f"the plugin printed nothing on stdout within {PLUGIN_START_TIMEOUT_SECS}s. "
            "The daemon reads the first line of output as the readiness signal and kills "
            "the process group when it does not come; the usual cause is block-buffered "
            "stdout."
        )
        assert "listening on port" in line, line

        registration = _wait_for_registration(daemon, process)
        assert registration.plugin_id == "spawned"
        assert registration.auth_token == daemon.auth_token
        assert registration.capabilities == ["tools"]
        assert registration.port > 0
    finally:
        process.terminate()
        out, err = process.communicate(timeout=30)
    assert "Registered successfully" in out, err


def test_an_argument_this_sdk_has_never_heard_of_is_not_fatal(daemon):
    """The one that would have killed every Python plugin in the field.

    Published 0.4.0 called `parser.parse_args()`, which prints
    `error: unrecognized arguments` and `sys.exit(2)` before the gRPC server
    binds. A daemon that appended one new flag would have stopped every
    installed Python plugin from starting, and no SDK release can rescue a build
    that is already installed. So an unknown flag is ignored, loudly.
    """
    process = _spawn(daemon, "--capability-negotiation-v9", "--verbose")
    try:
        registration = _wait_for_registration(daemon, process)
        assert registration.plugin_id == "spawned"
    finally:
        process.terminate()
        out, err = process.communicate(timeout=30)
    assert "Ignoring unrecognized arguments" in err
    assert "--capability-negotiation-v9" in err


def test_the_reserved_name_assertion_runs_before_anything_else(daemon):
    """`run()` refuses to start on a proto that revived a retired field name.

    Driven by pointing the check at a registry the loaded proto cannot satisfy,
    which is what a stale `plugin_pb2` earlier on `sys.path` looks like from
    inside the process. The assertion has to fire before the port is bound: a
    plugin that binds, registers and *then* discovers it is reading the wrong
    fields has already told the daemon it is healthy.
    """
    sdk_path = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    source = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {sdk_path!r})
        from astra_plugin_sdk import Plugin, ReservedNameError
        from astra_plugin_sdk import reserved

        reserved.REGISTRY = {{"AiSettings": frozenset({{"provider"}})}}

        try:
            Plugin().run()
        except ReservedNameError as e:
            print("REFUSED:", e, file=sys.stderr)
            sys.exit(78)
        raise SystemExit("the assertion did not fire")
        """
    )
    process = subprocess.run(
        [sys.executable, "-c", source, "--daemon-addr", daemon.address, "--plugin-id", "x"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 78, process.stderr
    assert "provider" in process.stderr
    assert daemon.registrations == [], "it bound and registered before checking"
