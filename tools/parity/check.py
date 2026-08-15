#!/usr/bin/env python3
"""Fail the build when `spec/hooks.yaml`, the proto, and the SDK sources disagree.

    python3 tools/parity/check.py            # all rules
    python3 tools/parity/check.py --rules R1,R4
    python3 tools/parity/check.py --astra-dir /path/to/Astra/astra-rs
    python3 tools/parity/check.py --fix-provenance   # re-point moved daemon_calls lines

Rules:
  R1  a hook is `stable` in the spec but the SDK has no binding for it
      (R1b: a hook is `n/a` in the spec but the SDK binds it after all)
  R2  an SDK binds an rpc that has no row in the spec
  R3  an rpc exists in the proto's plugin-facing services but in no spec row
      (R3b: a spec row names an rpc the proto does not declare;
       R3c: a row's `streaming` kind disagrees with the proto)
  R4  a `planned` row is past its `grace_until`
  R5  `daemon_calls` does not point at the call site it claims. Needs an Astra
      checkout ($ASTRA_RS_DIR, else ../Astra/astra-rs); skipped, loudly, without one.
  R6  a PluginHostService row's `permission` disagrees with the daemon's
      HOST_RPC_PERMISSIONS — the table `require_permission` reads. Same checkout,
      same loud skip.
  R7  a conformance report and the spec disagree. THE rule for "a hook cannot be
      committed as `stable` while returning UNIMPLEMENTED": R1 asks whether the
      SDK has a binding, R7 asks whether the binding reached anything when a real
      plugin process was driven through it. Needs
      `astra-plugin test --report <file>` output, passed as --report; skipped,
      loudly, without one.
      (R7b: an rpc the spec marks `n/a` was answered anyway;
       R7c: the report names an rpc no row mentions;
       R7d: the run was against a different protocol generation)

WHAT COUNTS AS A BINDING
Not "the name appears somewhere", and not "a method with the right name exists".
Each language has one anchored region — the gRPC service impl, the host-client
call surface — and only names found inside it count; then, for the
daemon→plugin direction, the dispatch target is RESOLVED and its body is read.
A handler whose body only answers `UNIMPLEMENTED` does NOT count, because on the
wire an `Unimplemented` reply is indistinguishable from an absent hook, and that
equivalence is the protocol's forward-compat contract.

Resolving the target matters because the registration and the work are in
different places in all three languages: TypeScript registers
`ListTools: this.wrapHandler(this.handleListTools.bind(this))` — one line, no
body — so a scanner that read only the map read nothing at all and the
UNIMPLEMENTED filter could never fire. It now follows `.bind(this)` to
`private async handleListTools(`, Python follows the `_CapabilityServicer`
method to its `self.plugin.<hook>` call, and Rust reads the `async fn` body in
`runner.rs`.

The judgement, per handler body, in order:

  1. it dispatches into the plugin's own surface  → a binding;
  2. otherwise, it mentions UNIMPLEMENTED         → NOT a binding;
  3. otherwise                                    → a binding.

Rule 3 is not laxity: `Shutdown` in Rust legitimately never touches
`self.plugin` (it trips the shutdown signal and `run_with` calls `on_shutdown`
once the server is down). What rule 2 catches is the stub — a handler replaced
by a bare `throw new HookUnimplemented(...)` — which is the shape this filter
was written for and, until now, could not see.

R1 answers "does the SDK bind this hook to something that does work". R7 — which
drives a real plugin process — answers "did that binding reach anything". Both,
because neither is the other.

If an anchor stops matching, this script fails loudly rather than reporting an
empty scan as a clean bill of health.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec  # noqa: E402

REPO_ROOT = spec.REPO_ROOT
ALL_RULES = ("R1", "R2", "R3", "R4", "R5", "R6", "R7")


class AnchorError(Exception):
    """A source-scan anchor stopped matching. Never silently downgraded."""


def snake(rpc: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", rpc).lower()


# ── source scanning ──────────────────────────────────────────────────────────

def _read(rel: str) -> tuple[str, list[str]]:
    path = REPO_ROOT / rel
    if not path.exists():
        raise AnchorError(f"{rel}: file is gone — update tools/parity/check.py")
    text = path.read_text(encoding="utf-8")
    return text, text.splitlines()


def _region(rel: str, start_re: str, end_re: str | None) -> list[str]:
    """Lines between the first `start_re` match and the next `end_re` match."""
    _, lines = _read(rel)
    start = next((i for i, l in enumerate(lines) if re.search(start_re, l)), None)
    if start is None:
        raise AnchorError(
            f"{rel}: the parity checker's anchor /{start_re}/ no longer matches. "
            f"The scan region moved; update tools/parity/check.py rather than trusting "
            f"an empty scan."
        )
    if end_re is None:
        return lines[start:]
    end = next((i for i in range(start + 1, len(lines)) if re.search(end_re, lines[i])), len(lines))
    return lines[start:end]


def _strip_comments(body: str, markers: tuple[str, ...]) -> str:
    """Drop comment lines, so a handler documented as "TODO: UNIMPLEMENTED" is
    judged on what it does rather than on what it says about itself."""
    kept = []
    for line in body.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(m) for m in markers):
            continue
        kept.append(line)
    return "\n".join(kept)


def _verdict(rpc: str, body: str, dispatch: re.Pattern[str], markers: tuple[str, ...]) -> bool:
    """Is this handler body a binding? See WHAT COUNTS AS A BINDING above."""
    code = _strip_comments(body, markers)
    if dispatch.search(code):
        return True
    return "UNIMPLEMENTED" not in code.upper()


def _blocks(lines: list[str], head: re.Pattern[str], close: str) -> dict[str, str]:
    """`{name: body}` for every `head` match, up to the next line equal to `close`.

    Brace-counting would be more general and less honest: these three files are
    rustfmt/black/prettier output, so the closing line of a method is exactly
    `close` and a body that does not end that way is a file whose shape has
    changed enough to want a human.
    """
    out: dict[str, str] = {}
    name: str | None = None
    body: list[str] = []
    for line in lines:
        m = head.match(line)
        if m:
            if name is not None:
                out[name] = "\n".join(body)
            name, body = m.group(1), []
            continue
        if name is None:
            continue
        if line == close:
            out[name] = "\n".join(body)
            name, body = None, []
            continue
        body.append(line)
    if name is not None:
        out[name] = "\n".join(body)
    return out


#: Rust: the handler hands the call to the author's trait impl.
_RUST_DISPATCH = re.compile(r"self\.plugin\.")
#: Python: same, through the servicer's `self.plugin`.
_PY_DISPATCH = re.compile(r"self\.plugin\.")
#: TypeScript: `this.<something>(`, where the something is not another handler
#: and not the wrapper itself — i.e. a method an author can override.
_TS_DISPATCH = re.compile(r"\bthis\.(?!handle[A-Z]|wrapHandler\b|overrides\b)([a-z]\w*)\s*\(")


def scan_rust_capability() -> dict[str, str]:
    rel = "astra-plugin-sdk/src/runner.rs"
    region = _region(rel, r"^impl.*PluginCapabilityService\b", r"^#\[cfg\(test\)\]")
    bodies = _blocks(region, re.compile(r"    async fn ([a-z_][a-z0-9_]*)\s*\("), "    }")
    if not bodies:
        raise AnchorError(f"{rel}: no `async fn` found in the service impl — the anchor moved")
    return {
        name: rel
        for name, body in bodies.items()
        if _verdict(name, body, _RUST_DISPATCH, ("//",))
    }


def scan_rust_host() -> dict[str, str]:
    """Two shapes, because one rpc now needs per-call metadata.

    The original shape is `client.rpc(proto::Message { .. })` — the message
    inline in the call. That was every host rpc until `FireTrigger` had to carry
    an invocation lease as gRPC metadata, which means building a
    `tonic::Request` first and passing it by name. Reading only the first shape
    made a live binding invisible: R1 reported `FireTrigger` as unimplemented in
    Rust while the SDK was calling it perfectly well.

    So the second shape is `let <name> = tonic::Request::new(proto::Message …)`
    followed by `.rpc(<name>)`. The staged names reset at every `pub async fn`,
    so a local called `request` in one method cannot vouch for a `.foo(request)`
    in another — the check has to stay able to fail.
    """
    rel = "astra-plugin-sdk/src/host_client.rs"
    region = _region(rel, r"^//!|^use |^pub |^impl ", r"^#\[cfg\(test\)\]")
    found = {}
    staged: set[str] = set()
    for line in region:
        if re.match(r"\s*(?:pub )?(?:async )?fn ", line):
            staged.clear()
        for m in re.finditer(r"\blet\s+(?:mut\s+)?(\w+)\s*=\s*tonic::Request::new\(\s*proto::", line):
            staged.add(m.group(1))
        for m in re.finditer(r"\.([a-z_][a-z0-9_]*)\(\s*proto::", line):
            found[m.group(1)] = rel
        for m in re.finditer(r"\.([a-z_][a-z0-9_]*)\(\s*(\w+)\s*\)", line):
            if m.group(2) in staged:
                found[m.group(1)] = rel
    return found


def scan_python_capability() -> dict[str, str]:
    rel = "astra-plugin-sdk-python/astra_plugin_sdk/plugin.py"
    region = _region(rel, r"^class _CapabilityServicer\b", None)
    # Python has no closing brace, so a method ends where the next one begins or
    # the class does. Collect by header, then cut each body at the first line
    # that is neither blank nor indented past the method.
    heads = [
        (i, m.group(1))
        for i, line in enumerate(region)
        if (m := re.match(r"    async def ([A-Z]\w*)\s*\(", line))
    ]
    if not heads:
        raise AnchorError(f"{rel}: no `async def <Rpc>(` in _CapabilityServicer — the anchor moved")
    found = {}
    for pos, (start, name) in enumerate(heads):
        stop = heads[pos + 1][0] if pos + 1 < len(heads) else len(region)
        body = "\n".join(region[start + 1 : stop])
        if _verdict(name, body, _PY_DISPATCH, ("#",)):
            found[snake(name)] = rel
    return found


def scan_python_host() -> dict[str, str]:
    rel = "astra-plugin-sdk-python/astra_plugin_sdk/host_client.py"
    text, _ = _read(rel)
    found = {}
    for m in re.finditer(r"_stub\.([A-Z]\w*)\s*\(", text):
        found[snake(m.group(1))] = rel
    if not found:
        raise AnchorError(f"{rel}: no `_stub.<Rpc>(` call found — the host-client shape changed")
    return found


def scan_ts_capability() -> dict[str, str]:
    """Handler-map keys, resolved to the method they `.bind(this)`, then judged.

    Every entry in the map is one line — `ListTools:
    this.wrapHandler(this.handleListTools.bind(this)),` — so there is no body at
    the registration site to read. The body is `private async
    handleListTools(`, elsewhere in the same file.
    """
    rel = "astra-plugin-sdk-ts/src/plugin.ts"
    region = _region(rel, r"private capabilityHandlers\(\)", r"as unknown as HandlerMap")
    targets: dict[str, str] = {}
    for line in region:
        m = re.match(r"      ([A-Z]\w*)\s*:\s*(.+)$", line)
        if not m:
            continue
        rpc, expr = m.group(1), m.group(2)
        bind = re.search(r"this\.(\w+)\.bind\(this\)", expr)
        if not bind:
            raise AnchorError(
                f"{rel}: `{rpc}` in capabilityHandlers() is not a `this.<method>.bind(this)`. "
                f"The scanner resolves the dispatch target to read its body; teach it this shape "
                f"rather than letting the entry count on its name alone."
            )
        targets[rpc] = bind.group(1)
    if not targets:
        raise AnchorError(f"{rel}: the capability handler map is empty — the anchor moved")

    _, lines = _read(rel)
    bodies = _blocks(
        lines,
        re.compile(r"  (?:private |protected |public )?(?:async )?(handle[A-Z]\w*)\s*\("),
        "  }",
    )
    found = {}
    for rpc, method in targets.items():
        if method not in bodies:
            raise AnchorError(
                f"{rel}: capabilityHandlers() binds `{rpc}` to `{method}`, which has no "
                f"`private {method}(` definition this scanner can find."
            )
        if _verdict(rpc, bodies[method], _TS_DISPATCH, ("//", "*", "/*")):
            found[snake(rpc)] = rel
    return found


def scan_ts_host() -> dict[str, str]:
    rel = "astra-plugin-sdk-ts/src/host-client.ts"
    declared = _region(rel, r"^const REQUIRED_METHODS", r"\] as const;")
    names = set(re.findall(r'"([A-Z]\w*)"', "\n".join(declared)))
    text, _ = _read(rel)
    names |= set(re.findall(r"(?:this\.)?stub\.([A-Z]\w*)\s*\(", text))
    names |= set(re.findall(r'this\.unary(?:<[^>]*>)?\(\s*"([A-Z]\w*)"', text))
    if not names:
        raise AnchorError(f"{rel}: no host method names found — the anchor moved")
    return {snake(n): rel for n in names}


SCANNERS = {
    ("rust", "daemon->plugin"): scan_rust_capability,
    ("rust", "plugin->daemon"): scan_rust_host,
    ("python", "daemon->plugin"): scan_python_capability,
    ("python", "plugin->daemon"): scan_python_host,
    ("typescript", "daemon->plugin"): scan_ts_capability,
    ("typescript", "plugin->daemon"): scan_ts_host,
}


# ── proto scanning ───────────────────────────────────────────────────────────

def scan_proto(rel: str) -> dict[str, tuple[str, str]]:
    """{Rpc: (service, streaming)} for the two plugin-facing services."""
    text, _ = _read(rel)
    out: dict[str, tuple[str, str]] = {}
    for service in spec.SERVICES:
        m = re.search(r"^service\s+" + service + r"\s*\{", text, re.M)
        if not m:
            raise AnchorError(f"{rel}: `service {service}` not found")
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[m.end():i]
        for rpc in re.finditer(
            r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?[\w.]+\s*\)\s*returns\s*\(\s*(stream\s+)?[\w.]+\s*\)",
            body,
        ):
            name, req_stream, res_stream = rpc.group(1), bool(rpc.group(2)), bool(rpc.group(3))
            kind = {
                (False, False): "unary",
                (False, True): "server",
                (True, False): "client",
                (True, True): "bidi",
            }[(req_stream, res_stream)]
            out[name] = (service, kind)
    return out


# ── rules ────────────────────────────────────────────────────────────────────

def rule_R1(doc, bindings) -> list[str]:
    fails = []
    for hook in doc["hooks"]:
        for lang in spec.LANGUAGES:
            bound = snake(hook["rpc"]) in bindings[lang]
            if hook[lang] == "stable" and not bound:
                fails.append(
                    f"R1  {hook['rpc']}: spec says {lang}=stable, but no binding is in "
                    f"{spec.LANGUAGE_LABELS[lang]}'s source. Either implement it or "
                    f"downgrade the row to `planned`/`n/a`."
                )
            elif hook[lang] == "n/a" and bound:
                fails.append(
                    f"R1b {hook['rpc']}: spec says {lang}=n/a "
                    f"(\"{hook.get(f'{lang}_reason', '')}\"), but "
                    f"{bindings[lang][snake(hook['rpc'])]} binds it. Promote the row to `stable`."
                )
    return fails


def rule_R2(doc, bindings) -> list[str]:
    known = {snake(h["rpc"]) for h in doc["hooks"]}
    directions = {snake(h["rpc"]): h["direction"] for h in doc["hooks"]}
    fails = []
    for lang in spec.LANGUAGES:
        for name, where in sorted(bindings[lang].items()):
            if name not in known:
                fails.append(
                    f"R2  {name}: {where} binds an rpc with no row in spec/hooks.yaml. "
                    f"Add the row (with its daemon call site) or delete the binding."
                )
    for lang in spec.LANGUAGES:
        for name, where in sorted(bindings[lang].items()):
            if name in known and directions[name] != bindings["_direction"][lang][name]:
                fails.append(
                    f"R2  {name}: {where} binds it as {bindings['_direction'][lang][name]}, "
                    f"but the spec says {directions[name]}."
                )
    return fails


def rule_R3(doc, proto_rpcs) -> list[str]:
    rows = {h["rpc"]: h for h in doc["hooks"]}
    fails = []
    for rpc, (service, kind) in sorted(proto_rpcs.items()):
        row = rows.get(rpc)
        if row is None:
            fails.append(
                f"R3  {rpc}: declared on {service} in {doc['proto']} and has no row in "
                f"spec/hooks.yaml. Every plugin-facing rpc needs one — an undeclared hook "
                f"is how the SDKs drifted in the first place."
            )
            continue
        if row["service"] != service:
            fails.append(f"R3b {rpc}: spec says {row['service']}, the proto says {service}.")
        if row["streaming"] != kind:
            fails.append(
                f"R3c {rpc}: spec says streaming={row['streaming']}, the proto says {kind}."
            )
    for rpc in sorted(rows):
        if rpc not in proto_rpcs:
            fails.append(
                f"R3b {rpc}: spec/hooks.yaml has a row for an rpc {doc['proto']} does not "
                f"declare on either plugin-facing service."
            )
    return fails


def rule_R4(doc, today: datetime.date) -> list[str]:
    fails = []
    for hook in doc["hooks"]:
        for lang in spec.LANGUAGES:
            if hook[lang] != "planned":
                continue
            deadline = spec.grace_until(hook, lang)
            if deadline and deadline < today:
                overdue = (today - deadline).days
                fails.append(
                    f"R4  {hook['rpc']}: {lang} was planned until {deadline} — {overdue} day(s) "
                    f"overdue (tracked in {hook[f'{lang}_issue']}). Ship it, or move the date "
                    f"deliberately and say why."
                )
    return fails


def _daemon_root(doc, astra_dir: Path) -> Path | None:
    root = astra_dir / Path(doc["astra_daemon_root"]).name
    if root.exists():
        return root
    root = astra_dir / "astra-daemon"
    return root if root.exists() else None


def _provenance_probe(hook: dict) -> tuple[re.Pattern, str]:
    name = snake(hook["rpc"])
    if hook["direction"] == "daemon->plugin":
        return re.compile(r"\." + name + r"\s*\("), "call site"
    return re.compile(r"async fn " + name + r"\s*\("), "handler"


def rule_R5(doc, astra_dir: Path | None) -> tuple[list[str], str | None]:
    if astra_dir is None:
        return [], (
            "R5  SKIPPED: no Astra checkout. Set $ASTRA_RS_DIR or put one at ../Astra/astra-rs. "
            "The `daemon_calls` provenance in spec/hooks.yaml is UNVERIFIED in this run."
        )
    root = _daemon_root(doc, astra_dir)
    if root is None:
        return [], f"R5  SKIPPED: {astra_dir} has no astra-daemon/ — provenance UNVERIFIED."

    fails = []
    # A line that merely MOVED is not a finding. The daemon's plugin host is edited
    # every phase, so pinning exact line numbers made R5 fail on work that had
    # nothing to do with parity — twice, and both times the fix was mechanical.
    # What R5 is actually for is the branch below it: the call site is GONE, meaning
    # the daemon stopped calling a hook the spec still calls routed. That stays a
    # hard failure. Drift is reported as a note and repaired by --fix-provenance.
    drifted = []
    for hook in doc["hooks"]:
        if hook["daemon_calls"] == "none":
            continue
        rel, _, lineno = str(hook["daemon_calls"]).rpartition(":")
        path = root / rel
        if not path.exists():
            fails.append(f"R5  {hook['rpc']}: {hook['daemon_calls']} — no such file under {root}")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        pattern, what = _provenance_probe(hook)
        idx = int(lineno) - 1
        if 0 <= idx < len(lines) and pattern.search(lines[idx]):
            continue
        elsewhere = [i + 1 for i, l in enumerate(lines) if pattern.search(l)]
        if elsewhere:
            drifted.append(f"{hook['rpc']} {rel}:{lineno}->{elsewhere[0]}")
        else:
            fails.append(
                f"R5  {hook['rpc']}: routing={hook['routing']} claims {hook['daemon_calls']}, "
                f"but no {what} for `{snake(hook['rpc'])}` exists anywhere in {rel}. Either the "
                f"daemon stopped calling this hook — in which case it is `unrouted`, and that is "
                f"a finding, not a line-number fix — or the provenance names the wrong file."
            )
    note = None
    if drifted:
        note = (
            f"R5  {len(drifted)} provenance line(s) drifted (the call site still exists, it just "
            f"moved): {', '.join(drifted[:6])}"
            + (f", +{len(drifted) - 6} more" if len(drifted) > 6 else "")
            + ". Not a failure. Run `check.py --fix-provenance` to re-point them."
        )
    return fails, note


def rule_R6(doc, astra_dir: Path | None) -> tuple[list[str], str | None]:
    """A host row's `permission` must be what `require_permission` actually reads.

    §5.6 gates the plugin->daemon direction on `[permissions]`, and the daemon
    holds that mapping in ONE table — `HOST_RPC_PERMISSIONS` in
    `astra-daemon/src/plugins/host_service.rs`, which its own test pins to
    `astra.proto`'s service block. This rule makes `spec/hooks.yaml` a third
    reader of that table rather than a second copy of it.

    It matters because the failure is silent in the worst direction. If the spec
    says a call needs nothing and the daemon gates it, the generated docs tell an
    author to ship a manifest that is denied on a user's machine. If the spec
    names a permission the daemon dropped, the consent sheet grows a checkbox
    that buys nothing — and boxes that protect nothing are how users learn to
    tick boxes.

    Parsed as text, not linked: this repo has no Rust toolchain requirement and
    CI runs it on a bare Python. Same optionality as R5 — no checkout, no check,
    said out loud.
    """
    if astra_dir is None:
        return [], (
            "R6  SKIPPED: no Astra checkout. Set $ASTRA_RS_DIR or put one at ../Astra/astra-rs. "
            "The `permission` column in spec/hooks.yaml is UNVERIFIED in this run."
        )
    root = _daemon_root(doc, astra_dir)
    if root is None:
        return [], f"R6  SKIPPED: {astra_dir} has no astra-daemon/ — permissions UNVERIFIED."

    path = root / "src/plugins/host_service.rs"
    if not path.exists():
        return [], f"R6  SKIPPED: {path} does not exist — permissions UNVERIFIED."
    text = path.read_text(encoding="utf-8", errors="replace")
    # Anchor on the DECLARATION, not on the first mention of the name. The
    # module doc comment names `HOST_RPC_PERMISSIONS` ~330 lines above the const,
    # so partitioning on the bare string started the scan inside prose and ran to
    # the first `];` anywhere after it — sweeping in whatever unrelated code
    # happened to sit in between. On a tree where that span held nothing shaped
    # like `("name", Something::Variant)` the bug was invisible; the first branch
    # to put three `("trigger", ConversationEvent::…)` tuples there produced
    # `R6  the daemon gates trigger`, which is not a thing the daemon does.
    #
    # A check whose anchor can match its own documentation is green for a reason
    # unrelated to what it is named after, which is worse than a check that
    # fails: it reports on a region nobody chose.
    m = re.search(r"^\s*(?:pub\s+)?(?:const|static)\s+HOST_RPC_PERMISSIONS\b", text, re.M)
    if m is None:
        return [f"R6  {path}: no `const HOST_RPC_PERMISSIONS` declaration — the anchor moved."], None
    body, _, _ = text[m.end():].partition("];")
    if not body:
        return [f"R6  {path}: HOST_RPC_PERMISSIONS is not terminated by `];` — the shape changed."], None

    # ("FireTrigger", Some(Permission::FireTrigger)) | ("Register", None)
    daemon: dict[str, str] = {}
    for rpc, arg in re.findall(r'\(\s*"(\w+)"\s*,\s*((?:Some\s*\(\s*)?[\w:]+)', body):
        variant = arg.rpartition("::")[2] if "::" in arg else None
        daemon[rpc] = snake(variant) if variant else "none"
    if not daemon:
        return [f"R6  {path}: HOST_RPC_PERMISSIONS parsed as empty — the shape changed."], None

    fails = []
    for hook in doc["hooks"]:
        if hook["service"] != "PluginHostService":
            continue
        rpc, declared = hook["rpc"], hook["permission"]
        actual = daemon.get(rpc)
        if actual is None:
            fails.append(
                f"R6  {rpc}: spec/hooks.yaml gates it on `{declared}`, but the daemon's "
                f"HOST_RPC_PERMISSIONS has no row for it at all. A host rpc with no row "
                f"is ungated — that is a security finding, not a spec typo."
            )
        elif actual != declared:
            fails.append(
                f"R6  {rpc}: spec/hooks.yaml says `permission: {declared}`, the daemon "
                f"requires `{actual}`. The daemon is authoritative — fix the row, and if "
                f"the daemon is the one that changed, the generated docs and the registry "
                f"bot's RPC_RULES have to move with it."
            )
    missing = sorted(set(daemon) - {h["rpc"] for h in doc["hooks"]})
    if missing:
        fails.append(
            f"R6  the daemon gates {', '.join(missing)}, which spec/hooks.yaml has no row "
            f"for. R3 covers rpcs in the proto; this covers rpcs the daemon really guards."
        )
    return fails, None


def rule_R7(doc, reports: list[Path]) -> tuple[list[str], str | None]:
    """The conformance runs and the spec must agree.

    R1-R6 read source. This reads what a plugin *did*, from the report
    `astra-plugin test --report` writes after driving a real plugin process
    through every hook its capabilities imply.

    It exists for one claim the static rules cannot make: **a hook cannot be
    committed as `stable` while returning UNIMPLEMENTED.** R1 asks whether the
    SDK has a binding; only a running plugin can answer whether the binding
    reaches anything. The two together are the whole statement.

    Four ways a report and the spec can disagree:

      R7   the spec says a hook is `required` and `stable` in this language,
           and the plugin answered UNIMPLEMENTED.
      R7b  the plugin answered an rpc the spec marks `n/a` for its language —
           the dynamic twin of R1b.
      R7c  the report names an rpc no spec row mentions — the dynamic twin of R2.
      R7d  the report's protocol generation is not the spec's.

    Optional hooks are exempt from R7 by construction, and that exemption is
    the forward-compatibility contract rather than an oversight: `Unimplemented`
    means *the hook is absent*, so a plugin that does not serve an optional hook
    is a plugin the daemon carries on without.

    Same optionality as R5 and R6: no report, no check, said out loud.
    """
    if not reports:
        return [], (
            "R7  SKIPPED: no conformance report. Produce one with "
            "`astra-plugin test --report <file>` and pass --report <file> — "
            "CONFORMANCE UNVERIFIED."
        )

    by_rpc = {h["rpc"]: h for h in doc["hooks"]}
    fails: list[str] = []

    for path in reports:
        if not path.exists():
            fails.append(f"R7  {path}: no such report.")
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fails.append(f"R7  {path}: not readable as JSON — {exc}")
            continue

        lang = report.get("language", "")
        # `typescript` is the spec's spelling; the CLI reports what it detected.
        lang = {"ts": "typescript", "py": "python"}.get(lang, lang)
        who = f"{report.get('plugin_id', path.name)} ({lang})"

        if lang not in spec.LANGUAGES:
            fails.append(
                f"R7  {who}: `language` is `{report.get('language')}`, which is not one of "
                f"{', '.join(spec.LANGUAGES)}. The report cannot be checked against a "
                f"per-language column."
            )
            continue

        declared_protocol = report.get("protocol")
        if declared_protocol is not None and declared_protocol != doc["protocol"]:
            fails.append(
                f"R7d {who}: the run was against protocol {declared_protocol}, "
                f"spec/hooks.yaml says {doc['protocol']}."
            )

        for hook in report.get("hooks", []):
            rpc, status = hook.get("rpc"), hook.get("status")
            row = by_rpc.get(rpc)
            if row is None:
                fails.append(
                    f"R7c {who}: exercised `{rpc}`, which has no row in spec/hooks.yaml."
                )
                continue
            declared = row.get(lang)
            if status == "unimplemented" and row.get("requirement") == "required":
                fails.append(
                    f"R7  {rpc}: spec/hooks.yaml says `requirement: required` and "
                    f"`{lang}: {declared}`, and {who} answered UNIMPLEMENTED. A hook cannot be "
                    f"committed as stable while returning UNIMPLEMENTED: protocol-wise "
                    f"Unimplemented means the hook is ABSENT, so this row is a promise the "
                    f"running code does not keep. Either implement it, or change the row."
                )
            if status == "ok" and declared == "n/a":
                fails.append(
                    f"R7b {rpc}: spec/hooks.yaml says `{lang}: n/a` "
                    f"({row.get(lang + '_reason', 'no reason given')}), and {who} answered it."
                )

        for failure in report.get("failures", []):
            fails.append(f"R7  {who}: the conformance run itself failed — {failure}")

    return fails, None


def fix_provenance(doc, astra_dir: Path | None) -> int:
    """Re-point `daemon_calls` at lines that merely moved.

    Deliberately narrow. It moves a line number when the same call site is
    findable elsewhere in the same file, and does NOTHING when a hook's call
    site has vanished — that is the daemon dropping a hook, and no tool should
    paper over it.
    """
    if astra_dir is None:
        print("--fix-provenance needs an Astra checkout; none found.", file=sys.stderr)
        return 2
    root = _daemon_root(doc, astra_dir)
    if root is None:
        print(f"--fix-provenance: {astra_dir} has no astra-daemon/.", file=sys.stderr)
        return 2

    text = spec.SPEC_PATH.read_text(encoding="utf-8")
    moved = 0
    for hook in doc["hooks"]:
        if hook["daemon_calls"] == "none":
            continue
        rel, _, lineno = str(hook["daemon_calls"]).rpartition(":")
        path = root / rel
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        pattern, _what = _provenance_probe(hook)
        idx = int(lineno) - 1
        if 0 <= idx < len(lines) and pattern.search(lines[idx]):
            continue
        hits = [i + 1 for i, l in enumerate(lines) if pattern.search(l)]
        if not hits:
            continue
        old = f'    daemon_calls: "{hook["daemon_calls"]}"'
        new = f'    daemon_calls: "{rel}:{hits[0]}"'
        if text.count(old) != 1:
            print(f"--fix-provenance: {hook['rpc']}: `{old.strip()}` is not unique; fix by hand.",
                  file=sys.stderr)
            continue
        text = text.replace(old, new)
        print(f"moved  {hook['rpc']}: {hook['daemon_calls']} -> {rel}:{hits[0]}")
        moved += 1
    if moved:
        spec.SPEC_PATH.write_text(text, encoding="utf-8")
        print(f"{moved} provenance line(s) re-pointed. Re-run `python3 tools/parity/gen.py`.")
    else:
        print("provenance: nothing to move.")
    return 0


# ── driver ───────────────────────────────────────────────────────────────────

def resolve_astra_dir(explicit: str | None) -> Path | None:
    """An explicit --astra-dir that does not exist is an error, not a quiet skip."""
    if explicit is not None:
        if not Path(explicit).is_dir():
            raise AnchorError(f"--astra-dir {explicit} is not a directory")
        return Path(explicit)
    for candidate in (os.environ.get("ASTRA_RS_DIR"), REPO_ROOT.parent / "Astra" / "astra-rs"):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rules", default=",".join(ALL_RULES), help="comma-separated subset, e.g. R1,R4")
    parser.add_argument("--astra-dir", default=None, help="path to Astra/astra-rs for R5 and R6")
    parser.add_argument("--today", default=None, help="ISO date, for testing R4")
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        metavar="FILE",
        help="a conformance report from `astra-plugin test --report`, for R7. Repeatable.",
    )
    parser.add_argument(
        "--fix-provenance",
        action="store_true",
        help="re-point daemon_calls at call sites that merely moved, then exit",
    )
    args = parser.parse_args(argv)

    selected = [r.strip() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in selected if r not in ALL_RULES]
    if unknown:
        print(f"unknown rule(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    try:
        doc = spec.load()
    except spec.SpecError as exc:
        print(f"spec/hooks.yaml is malformed:\n  {exc}", file=sys.stderr)
        return 2

    try:
        bindings: dict = {"_direction": {}}
        for lang in spec.LANGUAGES:
            merged: dict[str, str] = {}
            per_direction: dict[str, str] = {}
            for direction in ("daemon->plugin", "plugin->daemon"):
                for name, where in SCANNERS[(lang, direction)]().items():
                    merged[name] = where
                    per_direction[name] = direction
            bindings[lang] = merged
            bindings["_direction"][lang] = per_direction
        proto_rpcs = scan_proto(str(doc["proto"]))
    except AnchorError as exc:
        print(f"parity scan could not run:\n  {exc}", file=sys.stderr)
        return 2

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    try:
        astra_dir = resolve_astra_dir(args.astra_dir)
    except AnchorError as exc:
        print(f"parity scan could not run:\n  {exc}", file=sys.stderr)
        return 2

    if args.fix_provenance:
        return fix_provenance(doc, astra_dir)

    failures: list[str] = []
    skips: list[str] = []
    if "R1" in selected:
        failures += rule_R1(doc, bindings)
    if "R2" in selected:
        failures += rule_R2(doc, bindings)
    if "R3" in selected:
        failures += rule_R3(doc, proto_rpcs)
    if "R4" in selected:
        failures += rule_R4(doc, today)
    if "R5" in selected:
        r5, skip = rule_R5(doc, astra_dir)
        failures += r5
        if skip:
            skips.append(skip)

    if "R6" in selected:
        r6, skip = rule_R6(doc, astra_dir)
        failures += r6
        if skip:
            skips.append(skip)

    if "R7" in selected:
        r7, skip = rule_R7(doc, [Path(p) for p in args.report])
        failures += r7
        if skip:
            skips.append(skip)

    counts = ", ".join(
        f"{lang}={len(bindings[lang])}" for lang in spec.LANGUAGES
    )
    print(
        f"parity: {len(doc['hooks'])} spec rows, {len(proto_rpcs)} plugin-facing rpcs in "
        f"{doc['proto']}, bindings scanned: {counts}"
    )
    for skip in skips:
        print(skip)

    if failures:
        print(f"\n{len(failures)} parity failure(s):\n", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nspec/hooks.yaml is the source of truth. Fix the code, or fix the row and "
            "re-run `python3 tools/parity/gen.py`.",
            file=sys.stderr,
        )
        return 1

    print(f"parity: rules {', '.join(selected)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
