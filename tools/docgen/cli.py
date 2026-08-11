"""`docs/en/reference/cli.md` — the `astra-plugin` command line, from `clap`.

# Why this is generated from the binary and not from a doc page

The old `docs/en/cli.md` documented a `ui_panels` capability that never
existed, a scaffold path the CLI does not write, a build pipeline it does not
run and a `RUST_LOG` that did nothing. It was written once and the CLI moved
nine times. A reference page whose only tie to the tool is a human's memory is
the largest single source of documentation rot in this repository.

So this file does not describe the CLI. It *asks* it.

# The two readings, and why both are the clap definitions

1. **`astra-plugin <cmd> --help`, executed.** `clap` renders help from the very
   `#[derive(Parser)]` definitions it parses arguments with, so a flag that is
   not in the help is not a flag. This is the authority for names, value
   names, defaults, possible values and help text.

   The output is stable in CI: `astra-plugin-cli` depends on `clap` without the
   `wrap_help` feature, so there is no terminal-width dependence and no
   `COLUMNS` to pin. Verified by reading `astra-plugin-cli/Cargo.toml`, whose
   `clap` entry is `features = ["derive"]` and nothing else.

2. **`astra-plugin-cli/src/main.rs`, parsed.** For exactly the two facts help
   output cannot carry:

   * `#[command(alias = ...)]` — clap resolves an alias but never prints it,
     and `new`/`create` and `check`/`validate` are both real spellings an
     author's script may hold.
   * `#[arg(hide = true)]` — `build --no-sign` is a deprecated no-op that the
     pinned release workflow still passes. Hidden from `--help` on purpose, and
     precisely the kind of thing an author needs a reference for.

   Both are *verified against the binary*: every alias is executed and its help
   compared with the canonical command's, and every hidden flag is passed to a
   `--help` invocation of its command, which clap rejects if the flag does not
   exist. A source scan that has drifted from the binary therefore fails
   generation rather than printing a fiction.

If either reading yields nothing where the other says there should be
something, generation fails. See `DocgenError` in `common.py`.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from common import DocgenError, REPO_ROOT, banner, cell, paragraphs, read, run

MAIN_RS = "astra-plugin-cli/src/main.rs"
CARGO_TOML = "astra-plugin-cli/Cargo.toml"

#: Where a locally built CLI lands. `--release` first: it is what CI builds and
#: what `scaffold-roundtrip` puts on `$PATH`.
BIN_CANDIDATES = (
    "astra-plugin-cli/target/release/astra-plugin",
    "astra-plugin-cli/target/debug/astra-plugin",
)

#: Printed in every command's table anyway, so shown once at the top instead.
#: `--json` is global (`#[arg(long, global = true)]`) and `-h` is clap's own.
UBIQUITOUS = {"--json", "-h, --help", "-V, --version"}


# ── the binary ───────────────────────────────────────────────────────────────


def find_binary() -> Path:
    """The `astra-plugin` to interrogate.

    `$ASTRA_PLUGIN_BIN` wins, then a build in this tree, then `$PATH`. Never
    built implicitly: a generator that silently runs `cargo build` turns a
    thirty-second docs check into a five-minute one and hides which binary it
    read.
    """
    override = os.environ.get("ASTRA_PLUGIN_BIN")
    if override:
        path = Path(override)
        if not path.exists():
            raise DocgenError(f"$ASTRA_PLUGIN_BIN={override} does not exist.")
        return path
    for rel in BIN_CANDIDATES:
        for suffix in ("", ".exe"):
            path = REPO_ROOT / (rel + suffix)
            if path.exists():
                return path
    found = shutil.which("astra-plugin")
    if found:
        return Path(found)
    raise DocgenError(
        "no `astra-plugin` binary to read the clap definitions from. Build it:\n"
        "    cargo build --release --manifest-path astra-plugin-cli/Cargo.toml\n"
        "or point $ASTRA_PLUGIN_BIN at one."
    )


def assert_no_wrap_help() -> None:
    """`clap`'s `wrap_help` feature would make help output width-dependent.

    With it on, clap consults the terminal width (falling back to 100 columns)
    and re-flows every help string, so the same binary would generate a
    different `cli.md` under a different `$COLUMNS` and CI would fail for a
    reason that has nothing to do with the CLI. It is off today; this is the
    check that notices if it is ever turned on.
    """
    cargo = read(CARGO_TOML)
    match = re.search(r"^clap\s*=\s*(.+)$", cargo, re.MULTILINE)
    if not match:
        raise DocgenError(f"{CARGO_TOML}: no `clap` dependency line — the anchor moved.")
    if "wrap_help" in match.group(1):
        raise DocgenError(
            f"{CARGO_TOML} enables clap's `wrap_help`, which re-flows help text to the "
            f"terminal width. Generated help output would depend on $COLUMNS and this "
            f"check would fail wherever it was not 100. Pin the width in tools/docgen/cli.py "
            f"(clap reads `COLUMNS`) before turning it on."
        )


# ── help output ──────────────────────────────────────────────────────────────


@dataclass
class Entry:
    """One row of a clap `Arguments:` or `Options:` block."""

    spec: str
    help: str
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class Help:
    about: str
    usage: list[str]
    commands: list[tuple[str, str]]
    arguments: list[Entry]
    options: list[Entry]
    after: str


HEADER_RE = re.compile(r"^([A-Z][A-Za-z ]*):\s*$")
TAG_RE = re.compile(r"\[(default|possible values|aliases|short aliases|env|required):\s*([^\]]*)\]")


def _split_entries(lines: list[str]) -> list[Entry]:
    """Group an indented block into entries.

    clap starts a row at the block's own left margin when the argument has a
    short flag (`  -o, --output <OUTPUT>`) and four columns further in when it
    does not (`      --target <TARGET>`), so an entry begins at `margin` or
    `margin + 4`. Everything indented further belongs to the entry above it:
    the wrapped help of the short layout, or the ten-column help paragraphs of
    the long layout clap switches to when a command has a multi-paragraph doc
    comment.
    """
    body = [line for line in lines if line.strip()]
    if not body:
        return []
    margin = min(len(line) - len(line.lstrip()) for line in body)

    entries: list[Entry] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                current.append("")
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= margin + 4:
            if current:
                entries.append(_make_entry(current))
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(_make_entry(current))
    return entries


def _make_entry(lines: list[str]) -> Entry:
    first = lines[0].strip()
    rest = [line.strip() for line in lines[1:]]
    # Short layout: two or more spaces separate the spec from its help.
    parts = re.split(r"\s{2,}", first, maxsplit=1)
    if len(parts) == 2:
        spec, head = parts
        body = " ".join([head, *rest])
    else:
        spec, body = first, " ".join(rest)

    tags: dict[str, str] = {}
    for key, value in TAG_RE.findall(body):
        tags[key] = value.strip()
    body = TAG_RE.sub("", body)
    return Entry(spec=spec.strip(), help=" ".join(body.split()), tags=tags)


def parse_help(text: str) -> Help:
    lines = text.replace("\r\n", "\n").split("\n")
    about: list[str] = []
    usage: list[str] = []
    sections: dict[str, list[str]] = {}
    after: list[str] = []

    current: str | None = None
    seen_section = False
    for line in lines:
        header = HEADER_RE.match(line)
        if header:
            current = header.group(1)
            sections.setdefault(current, [])
            seen_section = True
            continue
        if line.startswith("Usage:"):
            usage.append(line[len("Usage:") :].strip())
            current = "Usage"
            seen_section = True
            continue
        if current == "Usage":
            # A second usage form is indented under the first.
            if line.startswith("  ") and line.strip():
                usage.append(line.strip())
                continue
            if not line.strip():
                current = None
                continue
        if current in sections:
            if line.strip() or sections[current]:
                sections[current].append(line)
            continue
        if not seen_section:
            about.append(line)
        else:
            after.append(line)

    commands = []
    for entry in _split_entries(sections.get("Commands", [])):
        commands.append((entry.spec.split()[0], entry.help))

    return Help(
        about=paragraphs("\n".join(about)),
        usage=usage,
        commands=commands,
        arguments=_split_entries(sections.get("Arguments", [])),
        options=_split_entries(sections.get("Options", [])),
        after=paragraphs("\n".join(after)),
    )


# ── main.rs: the two facts help output cannot carry ──────────────────────────


def kebab(variant: str) -> str:
    """clap's default subcommand rename. `InitCi` -> `init-ci`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", variant).lower()


@dataclass
class SourceFacts:
    aliases: dict[str, list[str]]
    hidden: dict[str, list[tuple[str, str]]]  # command -> [(flag, doc)]


def scan_main_rs() -> SourceFacts:
    """Aliases and hidden args, from the `Commands` enum.

    Text, not `syn`: this repository's CI runs the docs check on a bare Python,
    and every fact taken from here is independently verified against the binary
    before it reaches the page.
    """
    text = read(MAIN_RS)
    start = text.find("enum Commands {")
    if start < 0:
        raise DocgenError(f"{MAIN_RS}: `enum Commands {{` not found — the anchor moved.")
    body = text[start:]

    aliases: dict[str, list[str]] = {}
    hidden: dict[str, list[tuple[str, str]]] = {}

    variant: str | None = None
    pending_attrs: list[str] = []
    pending_docs: list[str] = []
    for raw in body.split("\n")[1:]:
        line = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if line == "}" and indent == 0:
            break

        if line.startswith("///"):
            pending_docs.append(line[3:].strip())
            continue
        if line.startswith("#["):
            pending_attrs.append(line)
            continue

        # A variant header: `New {`, at one level of indentation.
        variant_match = re.match(r"^([A-Z]\w*)\s*\{", line)
        if variant_match and indent == 4:
            variant = kebab(variant_match.group(1))
            for attr in pending_attrs:
                for alias in re.findall(r'alias\s*=\s*"([^"]+)"', attr):
                    aliases.setdefault(variant, []).append(alias)
            pending_attrs, pending_docs = [], []
            continue

        # A field inside a variant: the attributes just above it describe it.
        field_match = re.match(r"^(\w+)\s*:", line)
        if field_match and variant and pending_attrs:
            attr = " ".join(pending_attrs)
            if re.search(r"\bhide\s*=\s*true\b", attr):
                flag = f"--{field_match.group(1).replace('_', '-')}"
                hidden.setdefault(variant, []).append((flag, " ".join(pending_docs)))
        if line:
            pending_attrs, pending_docs = [], []

    if not aliases:
        raise DocgenError(
            f"{MAIN_RS}: no `#[command(alias = ...)]` found at all. `new` and `check` have "
            f"had one since 0.2; finding none means this scanner stopped matching the source."
        )
    if not hidden:
        raise DocgenError(
            f"{MAIN_RS}: no `#[arg(hide = true)]` found. `build --no-sign` is one; finding "
            f"none means this scanner stopped matching the source, not that hidden flags went "
            f"away — help output cannot tell you either way, which is why it is scanned here."
        )
    return SourceFacts(aliases=aliases, hidden=hidden)


def verify_alias(binary: Path, command: str, alias: str, canonical: str) -> None:
    """An alias must resolve to the same command, in the binary."""
    got = run([str(binary), alias, "--help"])
    if got != canonical:
        raise DocgenError(
            f"`astra-plugin {alias} --help` does not match `astra-plugin {command} --help`. "
            f"{MAIN_RS} declares `{alias}` as an alias of `{command}` and the binary disagrees."
        )


def verify_hidden(binary: Path, command: str, flag: str) -> None:
    """A hidden flag must still be accepted, in the binary.

    `--help` short-circuits before any work happens, so this proves the flag
    parses without running the command.
    """
    try:
        run([str(binary), command, flag, "--help"])
    except DocgenError as exc:
        raise DocgenError(
            f"{MAIN_RS} says `astra-plugin {command} {flag}` is a hidden argument, and the "
            f"binary rejects it:\n{exc}"
        ) from exc


# ── rendering ────────────────────────────────────────────────────────────────


def _entry_table(entries: list[Entry], *, title: str, head: str) -> list[str]:
    rows = [e for e in entries if e.spec not in UBIQUITOUS]
    if not rows:
        return []
    out = [f"{title}", "", f"| {head} | Description |", "|---|---|"]
    for entry in rows:
        detail = entry.help
        extras = []
        if "default" in entry.tags:
            extras.append(f"default `{entry.tags['default']}`")
        if "possible values" in entry.tags:
            values = ", ".join(f"`{v.strip()}`" for v in entry.tags["possible values"].split(","))
            extras.append(f"one of {values}")
        if "env" in entry.tags:
            extras.append(f"env `{entry.tags['env']}`")
        if extras:
            detail = f"{detail} ({'; '.join(extras)})" if detail else "; ".join(extras)
        out.append(f"| `{cell(entry.spec)}` | {cell(detail)} |")
    out.append("")
    return out


def render() -> str:
    assert_no_wrap_help()
    binary = find_binary()
    version = run([str(binary), "--version"]).strip()
    root = parse_help(run([str(binary), "--help"]))
    facts = scan_main_rs()

    if not root.commands:
        raise DocgenError("`astra-plugin --help` listed no commands — the parser broke.")

    commands = [name for name, _ in root.commands if name != "help"]
    for declared in facts.aliases:
        if declared not in commands:
            raise DocgenError(
                f"{MAIN_RS} declares aliases for `{declared}`, which `astra-plugin --help` "
                f"does not list. clap's subcommand renaming changed, or the variant was."
            )

    out = [
        banner(
            "cli.py",
            [
                "`astra-plugin --help` and one `--help` per subcommand, executed",
                f"{MAIN_RS} — `#[command(alias)]` and `#[arg(hide = true)]`, which clap never prints",
            ],
            extra=[f"Read from: {version}"],
        ),
        "# CLI reference",
        "",
        f"`{version}`. Every flag below was read out of the binary, so this page cannot "
        f"describe an option that does not exist. The source is "
        f"[`{MAIN_RS}`](../../../{MAIN_RS}).",
        "",
        root.about,
        "",
        "## Everywhere",
        "",
    ]

    global_rows = [e for e in root.options if e.spec in UBIQUITOUS]
    out += ["| Option | Description |", "|---|---|"]
    for entry in global_rows:
        out.append(f"| `{cell(entry.spec)}` | {cell(entry.help)} |")
    out.append("")
    if root.after:
        out += [root.after, ""]

    out += ["## Commands", "", "| Command | Aliases | What it does |", "|---|---|---|"]
    for name, summary in root.commands:
        if name == "help":
            continue
        alias_cell = ", ".join(f"`{a}`" for a in facts.aliases.get(name, [])) or "—"
        out.append(f"| [`{name}`](#astra-plugin-{name}) | {alias_cell} | {cell(summary)} |")
    out.append("")

    #: `no-login` is a design decision, and the module doc that states it is the
    #: only place it is written down in the CLI. Quoting it here is deliberate:
    #: the first question an author asks a plugin CLI is how to sign in.
    out += _no_login_note()

    for name in commands:
        text = run([str(binary), name, "--help"])
        help_ = parse_help(text)
        out += [f"## astra-plugin {name}", ""]
        aliases = facts.aliases.get(name, [])
        for alias in aliases:
            verify_alias(binary, name, alias, text)
        if aliases:
            out += [
                "Also spelled " + ", ".join(f"`astra-plugin {a}`" for a in aliases) + ".",
                "",
            ]
        if help_.about:
            out += [help_.about, ""]
        out += ["```", *[f"Usage: {u}" if i == 0 else f"       {u}" for i, u in enumerate(help_.usage)], "```", ""]
        out += _entry_table(help_.arguments, title="**Arguments**", head="Argument")
        out += _entry_table(help_.options, title="**Options**", head="Option")

        for flag, doc in facts.hidden.get(name, []):
            verify_hidden(binary, name, flag)
            out += [
                f"**Hidden: `{flag}`.** Accepted, and absent from `--help` "
                f"(`#[arg(hide = true)]`). {cell(doc)}",
                "",
            ]

    return "\n".join(out).rstrip() + "\n"


def _no_login_note() -> list[str]:
    """The `# The command set` paragraph from `main.rs`, quoted verbatim.

    Extracted rather than retyped: it is a claim about what the CLI does *not*
    have, and the one thing worse than an undocumented command is a documented
    command that was removed.
    """
    text = read(MAIN_RS)
    match = re.search(
        r"//! # The command set, and what is deliberately not in it\n(.*?)\n//!\n//! #",
        text,
        re.DOTALL,
    )
    if not match:
        raise DocgenError(
            f"{MAIN_RS}: the `# The command set` module-doc section is gone. It is the only "
            f"written statement that there is no `login`; docgen quotes it rather than "
            f"restating it."
        )
    body = "\n".join(line.removeprefix("//!").strip() for line in match.group(1).split("\n"))
    return ["### There is no `astra-plugin login`", "", paragraphs(body), ""]
