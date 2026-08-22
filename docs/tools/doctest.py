#!/usr/bin/env python3
"""Run every code sample in the written documentation.

    python3 docs/tools/doctest.py            # run everything
    python3 docs/tools/doctest.py --list     # what is there, and how each block runs
    python3 docs/tools/doctest.py --only rust-plugin,cli
    python3 docs/tools/doctest.py --strict   # skips are failures (this is what CI runs)

WHY THIS EXISTS
    `docs/en` landed in one commit and was never touched again while nine
    commits reshaped the CLI, the manifest, the proto and three SDKs. The
    largest class of the ~28 false claims the audit found was a code sample:
    a `plugin.toml` with a section the parser rejects, a `main.rs` written
    against a trait that had changed shape, a CLI line with a flag that does
    not exist. Prose drifts and a reader forgives it. A sample that does not
    compile costs an evening.

    So every fenced block in a written page carries a marker saying how it is
    checked, and this script checks it. A block with no marker is an error:
    the failure mode this replaces is a sample nobody thought about.

THE MARKER
    An HTML comment on the line immediately before the fence:

        <!-- doctest: rust-plugin -->
        ```rust
        use astra_plugin_sdk::prelude::*;
        ...
        ```

    Runners that EXECUTE the sample:

      rust-plugin      a complete `src/main.rs`. Built with `cargo build` in a
                       scaffolded project whose SDK is patched to this tree.
                       `test=1` additionally runs `cargo test`.
      toml-manifest    a complete `plugin.toml`. Run through
                       `astra-plugin check --strict`.
      cli              shell lines. Every `astra-plugin …` line is re-parsed by
                       the real binary (`--help` appended: clap validates the
                       subcommand and every flag, then exits before doing
                       anything). Other lines must use an allowlisted command.
                       The block is NOT executed as a script, so one thing it
                       cannot observe is checked structurally instead: a block
                       that unpacks the CLI archive and then calls `astra-plugin`
                       by bare name is refused, because for the reader — who by
                       definition has no CLI yet — that line is `command not
                       found`. Path-qualify it, or put the `cp` onto `PATH` in
                       the same block.
      python-plugin    a complete Python module. Byte-compiled, and executed
                       top-level when the SDK is importable.
      ts-plugin        a complete TypeScript module. Type-checked with `tsc
                       --noEmit` against this tree's SDK.
      json             parsed with `json.loads`.

    Runners that do NOT execute, and must say why:

      output           a transcript of a real command's output. Requires
                       `from="<the command that produced it>"`, and `from=` must
                       be a COMMAND, not a description of one. When it is an
                       `astra-plugin` line this harness can run — `--version`,
                       `--help`, `<sub> --help` — it IS run, and the block is
                       diffed against what it prints, with `<placeholders>`
                       matching anything. When it is not (it needs a project, a
                       daemon, the network, a specific machine), the block must
                       also carry `unrun="<why, and what to re-run by hand>"`:
                       nothing checks such a transcript, and the marker is where
                       that is admitted.
      illustrative     everything else, including a `from=` that is prose rather
                       than a command. Requires `reason="…"`. Use it for a
                       fragment that cannot compile alone, or for a file this
                       repository does not own.

EXIT CODES
    0  every block ran or was accounted for
    1  a sample is wrong
    2  the harness could not run a check (missing toolchain, and not --strict)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# Every language `docs/` carries. `en` is authoritative; the rest are
# file-for-file mirrors of it, so a sample is checked in each of them too —
# identical bytes are executed once and reported as `identical to` the English
# original, which is exactly how a sample that drifted in translation shows up.
#
# The tuple itself is in `locales.py` and only there. It used to be written out
# here, in `mirror.py` and in `ci.yml`, and all three spelled Chinese `zh-CN` —
# a code Astra cannot be set to and an author cannot ship. This script is run as
# `python3 docs/tools/doctest.py`, so its own directory is `sys.path[0]` and the
# import needs no path juggling.
from locales import LOCALES

ROOT = Path(__file__).resolve().parents[2]

#: Pages whose samples this script checks. Everything else under `docs/` is
#: either generated (and checked by its own generator's `--check`) or owned by
#: another tool.
INCLUDE = ("docs/README.md", *(f"docs/{loc}" for loc in LOCALES), "docs/tools")

#: Tiers inside INCLUDE that are NOT checked here, and why. Each is generated or
#: normative-by-hand and has its own drift check. The reason is a property of the
#: page, not of the language it is written in — `reference/cli.md` is generated
#: from the binary in every locale — so each entry is excluded in all of them.
EXCLUDE_TIERS = {
    "reference": "generated by tools/docgen — `python3 tools/docgen/gen.py --check`",
    "spec": "normative specs, owned by the spec author",
    "hooks": "generated by tools/parity/gen.py",
    "parity.md": "generated by tools/parity/gen.py",
}

EXCLUDE = {
    f"docs/{loc}/{tier}": why
    for loc in LOCALES
    for tier, why in EXCLUDE_TIERS.items()
}

MARKER_RE = re.compile(r"^<!--\s*doctest:\s*(?P<body>.*?)\s*-->\s*$")
ATTR_RE = re.compile(r'([\w-]+)(?:=(?:"([^"]*)"|(\S+)))?')
FENCE_RE = re.compile(r"^(?P<indent>\s*)(?P<fence>```+|~~~+)(?P<info>.*)$")

#: Commands a `cli` block may use besides `astra-plugin`. Every one of them is
#: shell context around the command being documented — a `cd` into the project,
#: the git commands that make a tag. They are NOT executed; they are allowed to
#: appear. Anything outside this list is a sample pretending to be a
#: transcript, and belongs in an `output` or `illustrative` block.
CLI_CONTEXT = {
    "cd", "git", "cargo", "mkdir", "cp", "mv", "ls", "cat", "export", "echo",
    "python3", "python", "pip", "node", "bun", "npm", "gh", "sha256sum",
    "certutil", "tar", "unzip", "code", "curl", "brew", "scoop", "winget",
    "RUST_LOG", "ASTRA_PLUGIN_WORKFLOW_SHA",
}


@dataclass
class Block:
    path: Path
    line: int
    runner: str
    attrs: dict
    lang: str
    body: str

    @property
    def rel(self) -> str:
        return str(self.path.relative_to(ROOT))

    @property
    def where(self) -> str:
        return f"{self.rel}:{self.line}"

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.runner}\0{sorted(self.attrs.items())}\0{self.body}".encode()
        ).hexdigest()[:12]


@dataclass
class Result:
    ok: int = 0
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    accounted: int = 0  # output/illustrative blocks with a stated reason


# ── extraction ───────────────────────────────────────────────────────────────


def parse_attrs(body: str) -> tuple[str, dict]:
    """`rust-plugin test=1` -> ("rust-plugin", {"test": "1"})."""
    parts = ATTR_RE.findall(body)
    if not parts:
        raise ValueError("empty doctest marker")
    runner = parts[0][0]
    attrs = {}
    for name, quoted, bare in parts[1:]:
        attrs[name] = quoted or bare or "1"
    return runner, attrs


def extract(path: Path) -> tuple[list[Block], list[str]]:
    """Every fenced block in one file, plus the ones with no marker."""
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[Block] = []
    unmarked: list[str] = []

    i = 0
    pending: tuple[str, dict] | None = None
    while i < len(lines):
        line = lines[i]
        m = MARKER_RE.match(line.strip())
        if m:
            try:
                pending = parse_attrs(m.group("body"))
            except ValueError as e:
                unmarked.append(f"{path.relative_to(ROOT)}:{i + 1}: {e}")
                pending = None
            i += 1
            continue

        f = FENCE_RE.match(line)
        if not f:
            # A blank line between the marker and the fence is fine; anything
            # else means the marker was not for this block.
            if line.strip():
                pending = None
            i += 1
            continue

        fence = f.group("fence")
        info = f.group("info").strip()
        start = i + 1
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not lines[i].strip().startswith(fence[0] * len(fence)):
            body_lines.append(lines[i])
            i += 1
        i += 1  # closing fence

        if pending is None:
            unmarked.append(
                f"{path.relative_to(ROOT)}:{start}: ```{info or '(no language)'} "
                f"has no <!-- doctest: … --> marker"
            )
        else:
            runner, attrs = pending
            blocks.append(
                Block(path, start, runner, attrs, info, "\n".join(body_lines) + "\n")
            )
        pending = None

    return blocks, unmarked


def discover(paths: list[str]) -> list[Path]:
    """Every default root must exist and contribute at least one page.

    `rglob` on a directory that is not there yields nothing and raises
    nothing, so a root that moved leaves no trace: the walk simply returns a
    smaller list, every block in it passes, and the run is green. Losing the
    `de` locale that way costs 24 files and 148 blocks and reports success —
    measured, by moving the directory and re-running, not supposed.

    The guard is per root rather than a floor on the total. A floor asks "did
    I find enough?", which needs a number somebody guessed and which a
    legitimately growing tree makes stale. `INCLUDE` is already an
    enumeration, so the stronger question is free: did I find *these*. It
    needs no number, it survives the docs growing, and it names the root that
    went missing instead of reporting a total that is merely lower than a
    guess.

    Explicit `paths` from the command line are exempt — asking for one file
    is not a claim about coverage.
    """
    out: list[Path] = []
    defaulted = not paths
    roots = [ROOT / p for p in (paths or INCLUDE)]
    missing: list[str] = []
    for root in roots:
        if root.is_file():
            out.append(root)
            continue
        found = 0
        for p in sorted(root.rglob("*.md")):
            rel = str(p.relative_to(ROOT))
            if any(rel == e or rel.startswith(e + "/") for e in EXCLUDE):
                continue
            out.append(p)
            found += 1
        if defaulted and found == 0:
            why = "does not exist" if not root.is_dir() else "contains no .md outside EXCLUDE"
            missing.append(f"{root.relative_to(ROOT)} — {why}")

    if missing:
        raise SystemExit(
            "doctest: a documentation root named in INCLUDE contributed nothing:\n"
            + "".join(f"  {m}\n" for m in missing)
            + "\nThis is refused rather than skipped. Every block that root held\n"
            "would otherwise go unchecked while this run reported success — the\n"
            "shape a doc-test can least afford, because its whole claim is that\n"
            "the samples on the page were executed.\n"
            "If the page set really did move, update INCLUDE in this file."
        )
    return out


# ── the environment the runners share ────────────────────────────────────────


class Env:
    def __init__(self, workdir: Path, build: bool):
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.build = build
        self._cli: Path | None = None
        self._rust_project: Path | None = None
        self._ts_project: Path | None = None
        self._python_ok: bool | None = None

    # -- astra-plugin ---------------------------------------------------------

    @property
    def cli(self) -> Path:
        if self._cli is not None:
            return self._cli
        env_bin = os.environ.get("ASTRA_PLUGIN_BIN")
        candidates = [Path(env_bin)] if env_bin else []
        candidates += [
            ROOT / "astra-plugin-cli/target/release/astra-plugin",
            ROOT / "astra-plugin-cli/target/release/astra-plugin.exe",
        ]
        for c in candidates:
            if c.is_file():
                self._cli = c
                return c
        if not self.build:
            raise Skip("astra-plugin is not built (pass no --no-build, or set ASTRA_PLUGIN_BIN)")
        run(["cargo", "build", "--release", "--manifest-path",
             str(ROOT / "astra-plugin-cli/Cargo.toml")], cwd=ROOT)
        return self.cli

    # -- a Rust project whose SDK is this tree --------------------------------

    @property
    def rust_project(self) -> Path:
        if self._rust_project is not None:
            return self._rust_project
        proj = self.workdir / "rust"
        if not (proj / "Cargo.toml").is_file():
            if shutil.which("cargo") is None:
                raise Skip("cargo is not on PATH")
            proj.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(proj, ignore_errors=True)
            run([str(self.cli), "new", "rust", "--lang", "rust", "--template", "tool",
                 "--output", str(proj)], cwd=self.workdir)
            # The scaffold pins the RELEASED SDK, which is not published yet.
            # Redirect resolution at this tree while leaving the declared range
            # alone — the same trick, and for the same reason, as the
            # scaffold-roundtrip job in .github/workflows/ci.yml.
            with (proj / "Cargo.toml").open("a", encoding="utf-8") as fh:
                fh.write(
                    "\n[patch.crates-io]\n"
                    f'astra-plugin-sdk = {{ path = "{(ROOT / "astra-plugin-sdk").as_posix()}" }}\n'
                )
        self._rust_project = proj
        return proj

    # -- a TypeScript project whose SDK is this tree --------------------------

    @property
    def ts_project(self) -> Path:
        if self._ts_project is not None:
            return self._ts_project
        sdk = ROOT / "astra-plugin-sdk-ts"
        tsc = sdk / "node_modules/.bin/tsc"
        if not tsc.is_file():
            raise Skip(
                "astra-plugin-sdk-ts/node_modules/.bin/tsc is missing — "
                "run `bun install` in astra-plugin-sdk-ts"
            )
        if not (sdk / "dist/index.d.ts").is_file():
            raise Skip(
                "astra-plugin-sdk-ts/dist is missing — run `bun run build` in "
                "astra-plugin-sdk-ts"
            )
        proj = self.workdir / "ts"
        (proj / "src").mkdir(parents=True, exist_ok=True)
        mods = proj / "node_modules"
        mods.mkdir(exist_ok=True)
        link = mods / "astra-plugin-sdk"
        if not link.exists():
            link.symlink_to(sdk, target_is_directory=True)
        # Everything else the sample can reach — @types/node, @grpc/* — comes
        # from the SDK's own tree, so a sample cannot type-check against a
        # dependency a real plugin would not have.
        (proj / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "commonjs",
                        "moduleResolution": "node",
                        "strict": True,
                        "skipLibCheck": True,
                        "noEmit": True,
                        "types": ["node"],
                        "typeRoots": [str((sdk / "node_modules/@types").as_posix())],
                        "baseUrl": ".",
                        "paths": {"*": [str((sdk / "node_modules/*").as_posix())]},
                    },
                    "include": ["src/**/*.ts"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self._ts_project = proj
        return proj

    #: The interpreter Python samples are executed with. Not necessarily the one
    #: running this script: the SDK needs `grpcio`, and the usual way to have it
    #: is a virtualenv. `ASTRA_DOCTEST_PYTHON=/path/to/venv/bin/python`.
    @property
    def python(self) -> str:
        return os.environ.get("ASTRA_DOCTEST_PYTHON") or sys.executable

    @property
    def python_sdk_importable(self) -> bool:
        if self._python_ok is None:
            p = subprocess.run(
                [self.python, "-c", "import astra_plugin_sdk"],
                cwd=ROOT / "astra-plugin-sdk-python",
                capture_output=True,
            )
            self._python_ok = p.returncode == 0
        return self._python_ok


class Skip(Exception):
    """The harness cannot run this check here. A failure under --strict."""


class Fail(Exception):
    """The sample is wrong."""


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise Fail(
            f"$ {' '.join(cmd)}\n(exit {p.returncode})\n"
            + tail(p.stdout)
            + tail(p.stderr)
        )
    return p


def tail(s: str, n: int = 40) -> str:
    lines = [ln for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    clipped = lines[-n:]
    prefix = f"… {len(lines) - len(clipped)} earlier line(s)\n" if len(lines) > len(clipped) else ""
    return prefix + "\n".join("    " + ln for ln in clipped) + "\n"


# ── runners ──────────────────────────────────────────────────────────────────


def run_rust_plugin(b: Block, env: Env) -> None:
    proj = env.rust_project
    (proj / "src/main.rs").write_text(b.body, encoding="utf-8")
    run(["cargo", "build", "--release", "--quiet"], cwd=proj)
    if b.attrs.get("test"):
        run(["cargo", "test", "--release", "--quiet"], cwd=proj)


def run_toml_manifest(b: Block, env: Env) -> None:
    d = env.workdir / "toml" / b.digest
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    (d / "plugin.toml").write_text(b.body, encoding="utf-8")
    run([str(env.cli), "check", str(d), "--strict"], cwd=d)


def is_cli_head(head: str) -> bool:
    """Whether this word invokes *this* repository's binary.

    A bare `astra-plugin` resolves through `PATH`; a path-qualified one —
    `./astra-plugin-0.2.1-linux-x64-musl/astra-plugin` — resolves out of the
    directory an archive just unpacked into. Both are the same program, and
    the second is the only form that works before anything is on `PATH`.
    """
    return PurePosixPath(head).name in ("astra-plugin", "astra-plugin.exe")


# A line that unpacks a release archive of the CLI. Everything after one of
# these, inside the same block, is running on a machine that does not yet have
# `astra-plugin` on its `PATH` — see `run_cli`.
UNPACKS_CLI_RE = re.compile(r"^(tar|unzip)\b.*astra-plugin-\S*\.(tar\.gz|tgz|zip)")
# ... unless the block itself puts the binary somewhere `PATH` will find it.
INSTALLS_CLI_RE = re.compile(r"^(cp|mv|install)\b.*astra-plugin.*\bbin\b")


def run_cli(b: Block, env: Env) -> None:
    cli = str(env.cli)
    checked = 0
    unpacked_here = False
    for raw in b.body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("$ ").strip()
        if UNPACKS_CLI_RE.match(line):
            unpacked_here = True
        elif INSTALLS_CLI_RE.match(line):
            unpacked_here = False
        # One line, one command: `&&`, `|` and `;` join commands that are each
        # checked on their own terms.
        for part in re.split(r"&&|\|\||;", line):
            part = part.strip()
            if not part:
                continue
            words = part.split()
            # Leading `NAME=value` tokens are environment, not the command:
            # `RUST_LOG=debug astra-plugin check` is an astra-plugin line.
            while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", words[0]):
                words = words[1:]
            if not words:
                continue
            head = words[0]
            if head == "astra-plugin" and unpacked_here:
                # The blind spot this harness had, made loud. A `cli` block is
                # never executed as a script — every `astra-plugin` line is
                # re-run on its own against a prebuilt binary at an absolute
                # path — so a block that unpacks the CLI and then calls it by
                # bare name passed here while exiting 127 for every reader,
                # who by definition does not have it on `PATH` yet.
                raise Fail(
                    f"`{part}` runs before anything is on `PATH`: this block unpacks the CLI "
                    "archive and never copies the binary into a `bin` directory, so a reader "
                    "pasting it gets `command not found` (exit 127). Write it path-qualified — "
                    "`./astra-plugin-<version>-<target>/astra-plugin --version` — or add the "
                    "`cp … ~/.local/bin/` line to this block."
                )
            if is_cli_head(head):
                # clap parses the subcommand and every flag, then `--help`
                # short-circuits before the subcommand does anything. An
                # unknown flag or subcommand exits 2 — which is the check.
                args = [a for a in words[1:] if a != "--help"]
                p = subprocess.run([cli, *args, "--help"], capture_output=True, text=True)
                if p.returncode != 0:
                    raise Fail(
                        f"`{part}` is not a command this CLI has:\n" + tail(p.stderr, 10)
                    )
                checked += 1
            elif head in CLI_CONTEXT or head.split("=")[0] in CLI_CONTEXT:
                continue
            else:
                raise Fail(
                    f"`{part}` is neither an astra-plugin command nor allowlisted shell "
                    f"context. Put it in an `output` or `illustrative` block, or add it to "
                    f"CLI_CONTEXT in {Path(__file__).relative_to(ROOT)} if it really is context."
                )
    if not checked:
        raise Fail("a `cli` block with no astra-plugin command in it")


def run_python_plugin(b: Block, env: Env) -> None:
    d = env.workdir / "python" / b.digest
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    f = d / "sample.py"
    f.write_text(b.body, encoding="utf-8")
    run([env.python, "-m", "py_compile", str(f)], cwd=d)
    if not env.python_sdk_importable:
        raise Skip(
            "the Python SDK is not importable here (needs grpcio); the sample was "
            "byte-compiled only. CI installs the wheel and runs it."
        )
    e = dict(os.environ)
    e["PYTHONPATH"] = str(ROOT / "astra-plugin-sdk-python") + os.pathsep + e.get("PYTHONPATH", "")
    # `run_name` is not "__main__", so a scaffold's `if __name__ == "__main__":
    # …run()` guard keeps the module from starting a server. Everything above
    # it — the imports, the class body, every decorator — really runs.
    #
    # Then every `def test_*` the sample defines is called, so a Python sample
    # can assert on its own behaviour the way the Rust ones do with `test=1`.
    # No pytest: a doc-test that needs a test runner installed is a doc-test
    # that gets skipped.
    driver = (
        "import runpy, sys\n"
        f"ns = runpy.run_path({str(f)!r}, run_name='astra_doctest')\n"
        "tests = [v for k, v in ns.items() if k.startswith('test_') and callable(v)]\n"
        "for t in tests:\n"
        "    t()\n"
        "    print('  ok', t.__name__)\n"
    )
    run([env.python, "-c", driver], cwd=d, env=e)


def run_ts_plugin(b: Block, env: Env) -> None:
    proj = env.ts_project
    src = proj / "src"
    for old in src.glob("*.ts"):
        old.unlink()
    (src / f"sample_{b.digest}.ts").write_text(b.body, encoding="utf-8")
    tsc = ROOT / "astra-plugin-sdk-ts/node_modules/.bin/tsc"
    run([str(tsc), "--noEmit", "-p", "tsconfig.json"], cwd=proj)


def run_json(b: Block, env: Env) -> None:
    try:
        json.loads(b.body)
    except json.JSONDecodeError as e:
        raise Fail(f"not valid JSON: {e}")


#: A `<placeholder>` in a transcript. Lower-case by convention, which is what
#: keeps it apart from clap's own `<COMMAND>` and `<FILE>` metavariables — those
#: are literal text in `--help` output and must match literally.
PLACEHOLDER_RE = re.compile(r"<[a-z][a-z0-9-]*>")

#: Flags that make an `astra-plugin` line safe to execute here: clap answers
#: them itself and exits before the subcommand touches the filesystem, the
#: network or a daemon. Anything else — `init-ci`, `doctor .`, `build .` — needs
#: a project, a machine or a running Astra that this harness does not have, and
#: is accounted for through `unrun=` instead of being run.
SELF_ANSWERING = {"--help", "-h", "--version", "-V"}


def output_command(b: Block) -> list[str]:
    """The command in `from=`, as words, with any trailing prose clause cut.

    `from="astra-plugin test . --no-build, in a scaffolded plugin"` is a command
    plus a note about where it was run. The comma is the seam, and everything
    before it has to be a command — prose all the way through belongs in an
    `illustrative` block, which is the distinction this function exists to keep.
    """
    text = b.attrs.get("from", "").split(", ", 1)[0].strip()
    words = text.split()
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", words[0]):
        words = words[1:]
    return words


def transcript_matches(expected: str, actual: str) -> bool:
    """The body, with `<placeholders>` standing in for whatever varies."""
    # Normalise BEFORE escaping: rstrip()ing a line of the finished pattern can
    # cut the trailing half of an escape sequence and make it uncompilable.
    norm = lambda s: "\n".join(ln.rstrip() for ln in s.strip().splitlines())
    parts = PLACEHOLDER_RE.split(norm(expected))
    pattern = ".+?".join(re.escape(p) for p in parts)
    return re.fullmatch(pattern, norm(actual), flags=re.DOTALL) is not None


def run_output(b: Block, env: Env) -> None:
    """A transcript. Run the command it names, when running it is possible.

    This used to check only that `from=` was a non-empty string, which meant a
    transcript could say anything at all and the gate stayed green — and one
    did: a block marked `from="cargo install … --root <scratch> …"` whose body
    claimed cargo had installed into `~/.cargo/bin`, which that command cannot
    print. So `from=` is now executed and diffed whenever the harness can
    execute it, and where it cannot, the block has to say so out loud rather
    than being waved through.
    """
    if not b.attrs.get("from"):
        raise Fail(
            'an `output` block must say what produced it: '
            '<!-- doctest: output from="astra-plugin check" -->'
        )
    words = output_command(b)
    if not words:
        raise Fail("`from=` is empty once the trailing note is removed")

    if words[0] != "astra-plugin":
        # Not this repository's binary, so the harness has no standing to run
        # it. It still has to be a command rather than a description.
        if words[0] not in CLI_CONTEXT:
            raise Fail(
                f"`from=\"{b.attrs['from']}\"` does not start with a command "
                f"(`{words[0]}` is neither astra-plugin nor allowlisted shell "
                "context). A description of how output was obtained is not a "
                "command — use an `illustrative` block with a `reason=`."
            )
        require_unrun(b)
        return

    if not set(words[1:]) & SELF_ANSWERING or any(
        not w.startswith("-") for w in words[1:]
    ):
        # A real astra-plugin command, but one that needs a project, a daemon or
        # a machine state this harness does not have.
        require_unrun(b)
        return

    p = subprocess.run(
        [str(env.cli), *words[1:]], capture_output=True, text=True
    )
    actual = p.stdout + p.stderr
    if not transcript_matches(b.body, actual):
        raise Fail(
            f"$ {' '.join(words)}\nthe block does not match what that prints "
            "(`<placeholders>` match anything):\n"
            + tail(actual)
        )


def require_unrun(b: Block) -> None:
    """A transcript this harness will not reproduce must say why, in the marker.

    Without this the un-run case is indistinguishable from the run one in the
    output, and `0 failed` reads as `every transcript was checked`. It never
    was: the summary now separates the two counts, and this is what keeps the
    un-run half honest about being un-run.
    """
    why = b.attrs.get("unrun", "")
    if len(why) < 12:
        raise Fail(
            f"`from=\"{b.attrs['from']}\"` names a command this harness cannot "
            "run here, so the transcript is not checked by anything. Say so in "
            'the marker: <!-- doctest: output from="…" unrun="why not — what a '
            'reader should re-run by hand" -->'
        )


def output_was_executed(b: Block) -> bool:
    """Whether `run_output` really ran the command, for the summary counts."""
    words = output_command(b)
    return (
        bool(words)
        and words[0] == "astra-plugin"
        and bool(set(words[1:]) & SELF_ANSWERING)
        and all(w.startswith("-") for w in words[1:])
    )


def run_illustrative(b: Block, env: Env) -> None:
    reason = b.attrs.get("reason", "")
    if len(reason) < 12:
        raise Fail(
            'an `illustrative` block must carry a real reason it cannot run: '
            '<!-- doctest: illustrative reason="…" -->'
        )


RUNNERS = {
    "rust-plugin": run_rust_plugin,
    "toml-manifest": run_toml_manifest,
    "cli": run_cli,
    "python-plugin": run_python_plugin,
    "ts-plugin": run_ts_plugin,
    "json": run_json,
    "output": run_output,
    "illustrative": run_illustrative,
}
EXECUTED = {"rust-plugin", "toml-manifest", "cli", "python-plugin", "ts-plugin", "json"}


def executes(b: Block) -> bool:
    """Did this block's check actually run something?

    `output` is in both camps: the ones whose `from=` is a self-answering
    `astra-plugin` line are executed and diffed, the rest are declared un-run.
    The summary counts them apart, so `0 failed` never has to be read as a
    claim about blocks nothing ran.
    """
    if b.runner in EXECUTED:
        return True
    return b.runner == "output" and output_was_executed(b)


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*",
                    help="files or directories (default: docs/README.md, "
                         "docs/{" + ",".join(LOCALES) + "}, docs/tools)")
    ap.add_argument("--list", action="store_true", help="print the blocks and exit")
    ap.add_argument("--only", help="comma-separated runner names")
    ap.add_argument("--strict", action="store_true", help="a skipped check is a failure")
    ap.add_argument("--no-build", action="store_true", help="never invoke cargo build for the CLI")
    ap.add_argument("--workdir", help="where the scratch projects live")
    args = ap.parse_args()

    files = discover(args.paths)
    blocks: list[Block] = []
    unmarked: list[str] = []
    for f in files:
        b, u = extract(f)
        blocks += b
        unmarked += u

    only = set(args.only.split(",")) if args.only else None
    if only:
        unknown = only - set(RUNNERS)
        if unknown:
            print(f"unknown runner(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        blocks = [b for b in blocks if b.runner in only]

    if args.list:
        for b in blocks:
            attrs = " ".join(f"{k}={v!r}" for k, v in b.attrs.items())
            print(f"{b.where:<52} {b.runner:<14} {attrs}")
        print(f"\n{len(blocks)} block(s) in {len(files)} file(s)")
        if unmarked:
            print(f"{len(unmarked)} unmarked block(s)")
        return 0

    if unmarked:
        print("Every fenced block in a written page needs a doctest marker.\n")
        for u in unmarked:
            print(f"  {u}")
        print(
            "\nAdd one of: "
            + ", ".join(sorted(RUNNERS))
            + "\n  <!-- doctest: cli -->\n"
            '  <!-- doctest: illustrative reason="why it cannot run" -->'
        )
        return 1

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.gettempdir()) / "astra-doctest"
    env = Env(workdir, build=not args.no_build)
    res = Result()
    seen: dict[str, str] = {}

    for b in blocks:
        runner = RUNNERS.get(b.runner)
        if runner is None:
            res.failed.append((b, f"unknown runner `{b.runner}`; have: {', '.join(sorted(RUNNERS))}"))
            print(f"FAIL {b.where}  unknown runner `{b.runner}`")
            continue
        if b.digest in seen and executes(b):
            # The Russian pages carry the same samples as the English ones.
            # Building the same `main.rs` twice proves nothing and costs a
            # minute; that they are byte-identical is the point.
            print(f"same {b.where:<52} {b.runner} (identical to {seen[b.digest]})")
            res.ok += 1
            continue
        try:
            runner(b, env)
        except Skip as e:
            res.skipped.append((b, str(e)))
            print(f"SKIP {b.where:<52} {b.runner}: {e}")
            continue
        except Fail as e:
            res.failed.append((b, str(e)))
            print(f"FAIL {b.where:<52} {b.runner}\n{e}")
            continue
        seen.setdefault(b.digest, b.where)
        if executes(b):
            res.ok += 1
            note = f": {b.attrs['from']}" if b.runner == "output" else ""
            print(f"ok   {b.where:<52} {b.runner}{note}")
        else:
            res.accounted += 1
            note = b.attrs.get("from") or b.attrs.get("reason", "")
            print(f"--   {b.where:<52} {b.runner}: {note}")

    print(
        f"\n{res.ok} executed · {res.accounted} accounted for (output/illustrative) · "
        f"{len(res.skipped)} skipped · {len(res.failed)} failed"
    )
    print(
        "`accounted for` means a stated reason was checked, not the sample. An "
        "`output` block\ncounts as executed only when its `from=` is an "
        "astra-plugin line this harness can run."
    )
    if res.failed:
        print("\nFAILED:")
        for b, why in res.failed:
            print(f"  {b.where}  ({b.runner})")
        return 1
    if res.skipped and args.strict:
        print("\n--strict: a skipped check is a failure. Install what it named.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
