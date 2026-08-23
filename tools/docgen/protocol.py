"""`docs/en/reference/protocol.md` — the gRPC surface, from `proto/plugin.proto`.

Three things a protocol reference has to get right, and one of them does not
live in this repository:

  * **services and RPCs** — from `proto/plugin.proto`, which is itself a
    generated slice of Astra's `astra.proto`, cut by the allowlist in
    `astra-proto/plugin-surface.toml`. Its header carries the protocol integer
    and the sha256 of the astra.proto it was cut from.
  * **streaming kind** — from the same file, and cross-checked against the
    `streaming` column of `spec/hooks.yaml` for every plugin-facing RPC. Two
    readers of one fact; generation fails if they disagree.
  * **the permission each host RPC is gated on** — which lives in the *daemon*,
    in `HOST_RPC_PERMISSIONS` in `astra-daemon/src/plugins/host_service.rs`, the
    table `require_permission` reads. This repository cannot see it, so the page
    takes the column from `spec/hooks.yaml` and says so. Parity rule R6 is what
    makes that safe: it parses the daemon's table out of an Astra checkout and
    fails when a row here disagrees, in either direction — a spec that says
    `none` where the daemon gates produces an author whose plugin is denied on a
    user's machine, and a spec that names a permission the daemon dropped
    produces a consent checkbox that buys nothing.

`PluginService` is included even though no plugin ever calls it: the daemon
serves it to the Astra UI, and it is where install, import, provenance and
consent live. An author reading about how their plugin reaches a user needs the
names in it. It is marked as what it is.
"""

from __future__ import annotations

import hashlib
import re

from common import DocgenError, banner, cell, code, read, REPO_ROOT

PROTO = "proto/plugin.proto"
VERSION_FILE = "proto/PROTO_VERSION"

PLUGIN_FACING = ("PluginCapabilityService", "PluginHostService")

SERVICE_NOTES = {
    "PluginCapabilityService": (
        "**Your plugin serves this.** The daemon is the client: it calls in to run a tool, "
        "synthesize speech, hand you an event. Every RPC here is a hook you implement, and "
        "`UNIMPLEMENTED` is the protocol's word for *this plugin does not have that hook* — "
        "not for an error."
    ),
    "PluginHostService": (
        "**The daemon serves this.** Your plugin is the client. `Register` is the "
        "bootstrap: it proves the spawn token the daemon passed the process and hands back "
        "a session token, and it is the one path the daemon's auth interceptor exempts. "
        "Every other call carries that token, and the gated ones are additionally checked "
        "against the permissions the *user* granted — a different question from the "
        "capabilities you declared."
    ),
    "PluginService": (
        "**Neither side of a plugin.** The daemon serves it to the Astra UI: install, "
        "import, uninstall, provenance, consent, logs. No plugin ever calls it and no SDK "
        "binds it; it is here because it is the surface a user's install of your plugin "
        "actually travels through."
    ),
}


def header_facts(text: str) -> dict[str, str]:
    """The generated header's `// key: value` lines.

    `protocol` and `surface-sha256` are required. `source-sha256` is not: it
    names the `astra.proto` the slice was cut from, it moves on every edit to
    that file including ones with no effect on this repository, and it is being
    retired to a sidecar in Astra where the source it describes actually lives.
    A reader here cannot verify it in any case — the file it names is private.

    `surface-sha256` is the opposite and is why the requirement moved: it is the
    digest of this file's own plugin-facing body, so anybody holding these bytes
    can check it, and it moves only when something a plugin can see moves.
    """
    facts = {}
    for key in ("protocol", "surface-sha256"):
        match = re.search(rf"^//\s*{re.escape(key)}:\s*(\S+)\s*$", text, re.MULTILINE)
        if not match:
            raise DocgenError(
                f"{PROTO}: the generated header has no `// {key}:` line. That header is what "
                f"tells a reader which protocol generation this file is; docgen will not "
                f"guess it."
            )
        facts[key] = match.group(1)
    optional = re.search(r"^//\s*source-sha256:\s*(\S+)\s*$", text, re.MULTILINE)
    if optional:
        facts["source-sha256"] = optional.group(1)
    return facts


def pinned_version() -> dict[str, str]:
    out = {}
    for line in read(VERSION_FILE).split("\n"):
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    if "protocol" not in out or "sha256" not in out:
        raise DocgenError(f"{VERSION_FILE}: no `protocol=` / `sha256=` — the format changed.")
    return out


RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(stream\s+)?([\w.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([\w.]+)\s*\)"
    r"\s*(\{.*?\}|;)",
    re.DOTALL,
)


def streaming_kind(req_stream: bool, res_stream: bool) -> str:
    if req_stream and res_stream:
        return "bidi"
    if res_stream:
        return "server"
    if req_stream:
        return "client"
    return "unary"


def leading_comment(text: str, end: int) -> str:
    """The `//` block immediately above the item ending at `end`."""
    lines = text[:end].split("\n")
    out: list[str] = []
    for line in reversed(lines[:-1]):
        stripped = line.strip()
        if stripped.startswith("//"):
            body = stripped.removeprefix("//").strip()
            if body.startswith("─") or set(body) == {"="}:
                break
            out.insert(0, body)
        elif not stripped:
            break
        else:
            break
    return " ".join(" ".join(out).split())


def summary(comment: str) -> str:
    if not comment:
        return "—"
    match = re.search(r"^(.+?[.!?])(\s|$)", comment)
    return match.group(1) if match else comment


def parse_services(text: str) -> dict[str, list[dict]]:
    services: dict[str, list[dict]] = {}
    for match in re.finditer(r"^service\s+(\w+)\s*\{", text, re.MULTILINE):
        name = match.group(1)
        depth = 0
        i = match.end() - 1
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    body = text[i + 1 : j]
                    break
        else:  # pragma: no cover
            raise DocgenError(f"{PROTO}: service {name} has unbalanced braces.")
        rpcs = []
        for rpc in RPC_RE.finditer(body):
            comment = leading_comment(body, rpc.start())
            rpcs.append(
                {
                    "name": rpc.group(1),
                    "request": rpc.group(3),
                    "response": rpc.group(5),
                    "streaming": streaming_kind(bool(rpc.group(2)), bool(rpc.group(4))),
                    "deprecated": "deprecated = true" in rpc.group(6),
                    "comment": comment,
                }
            )
        if not rpcs:
            raise DocgenError(f"{PROTO}: service {name} parsed with no RPCs.")
        services[name] = rpcs
    if not services:
        raise DocgenError(f"{PROTO}: no services parsed — the file's shape changed.")
    return services


def _hooks():
    import parity

    _, spec = parity._load()
    return spec.load()


def cross_check(services: dict[str, list[dict]], doc: dict) -> None:
    """The proto and `spec/hooks.yaml` must agree about the plugin-facing RPCs.

    Presence is parity rule R3's job and it runs in CI; streaming is nobody
    else's, and it is the column an SDK author reads to decide whether a hook
    returns a value or a stream. Two independent readers, one fact.
    """
    by_rpc = {(h["service"], h["rpc"]): h for h in doc["hooks"]}
    problems = []
    for service in PLUGIN_FACING:
        for rpc in services[service]:
            hook = by_rpc.get((service, rpc["name"]))
            if hook is None:
                problems.append(
                    f"{service}.{rpc['name']} is in {PROTO} and has no row in spec/hooks.yaml"
                )
                continue
            if hook["streaming"] != rpc["streaming"]:
                problems.append(
                    f"{service}.{rpc['name']}: {PROTO} says {rpc['streaming']}, "
                    f"spec/hooks.yaml says {hook['streaming']}"
                )
    for (service, rpc_name) in by_rpc:
        if rpc_name not in {r["name"] for r in services.get(service, [])}:
            problems.append(f"spec/hooks.yaml has {service}.{rpc_name}, {PROTO} does not")
    if problems:
        raise DocgenError(
            "the proto and spec/hooks.yaml disagree:\n  " + "\n  ".join(problems)
        )


def render() -> str:
    text = read(PROTO)
    facts = header_facts(text)
    pinned = pinned_version()
    digest = hashlib.sha256((REPO_ROOT / PROTO).read_bytes()).hexdigest()
    if digest != pinned["sha256"]:
        raise DocgenError(
            f"{VERSION_FILE} pins sha256={pinned['sha256']} and {PROTO} hashes to {digest}. "
            f"`tools/check-proto.sh` owns that invariant; docgen will not publish a "
            f"protocol reference for a proto that is not the pinned one."
        )
    if facts["protocol"] != pinned["protocol"]:
        raise DocgenError(
            f"{PROTO} header says protocol {facts['protocol']}, {VERSION_FILE} says "
            f"{pinned['protocol']}."
        )

    services = parse_services(text)
    doc = _hooks()
    cross_check(services, doc)

    permissions = {
        h["rpc"]: h.get("permission", "none")
        for h in doc["hooks"]
        if h["service"] == "PluginHostService"
    }
    capabilities = {(h["service"], h["rpc"]): h["capability"] for h in doc["hooks"]}
    routing = {(h["service"], h["rpc"]): h["routing"] for h in doc["hooks"]}
    # `spec/hooks.yaml` carries a one-line summary per plugin-facing hook,
    # written for an author and kept honest by rules R1-R7. The proto's own
    # comment is written for whoever implements the daemon side, and half the
    # hooks have none at all — every `rpc ListTools` sits under a `── Tools ──`
    # banner comment and nothing else. So the spec's line wins where it exists.
    summaries = {(h["service"], h["rpc"]): h["summary"] for h in doc["hooks"]}

    total = sum(len(v) for v in services.values())
    out = [
        banner(
            "protocol.py",
            [
                f"{PROTO} — services, RPCs, streaming kind, deprecations",
                f"{VERSION_FILE} — the protocol integer and the pinned digest",
                    "spec/hooks.yaml — `permission`, `routing` and `summary` for the two "
                "plugin-facing services; its `permission` column is pinned to the daemon's "
                "own HOST_RPC_PERMISSIONS by parity rule R6",
            ],
        ),
        "# Protocol reference",
        "",
        f"Protocol generation **{facts['protocol']}**. "
        f"{len(services)} services, {total} RPCs. Source: "
        f"[`{PROTO}`](../../../{PROTO}), a generated slice of Astra's `astra.proto` "
        f"(`surface-sha256: {facts['surface-sha256'][:16]}…`, the digest of the "
        f"plugin-facing body you are reading about), pinned by "
        f"[`{VERSION_FILE}`](../../../{VERSION_FILE}) at "
        f"`sha256:{pinned['sha256'][:16]}…`. Every vendored copy in the three SDKs has that "
        f"same hash; `tools/check-proto.sh` is what says so.",
        "",
        "## The three plugin services",
        "",
        "| Service | Direction | RPCs | Who serves it |",
        "|---|---|---|---|",
        f"| [`PluginCapabilityService`](#plugincapabilityservice) | daemon → plugin | "
        f"{len(services['PluginCapabilityService'])} | your plugin |",
        f"| [`PluginHostService`](#pluginhostservice) | plugin → daemon | "
        f"{len(services['PluginHostService'])} | the daemon |",
        f"| [`PluginService`](#pluginservice) | UI → daemon | "
        f"{len(services['PluginService'])} | the daemon |",
        "",
        "The protocol generation is the contract. A plugin sends it in "
        "`PluginRegisterRequest.protocol_version` and the daemon answers with its own floor "
        "in `PluginRegisterResponse.min_supported_protocol`; `sdk_name` and `sdk_version` "
        "ride along for triage and gate nothing.",
        "",
    ]

    for service in ("PluginCapabilityService", "PluginHostService", "PluginService"):
        rpcs = services[service]
        out += [f"## {service}", "", SERVICE_NOTES[service], ""]
        host = service == "PluginHostService"
        if host:
            out += [
                "| RPC | Permission | Request | Response | Stream | Routed | What it does |",
                "|---|---|---|---|---|---|---|",
            ]
        elif service == "PluginCapabilityService":
            out += [
                "| RPC | Capability | Request | Response | Stream | Routed | What it does |",
                "|---|---|---|---|---|---|---|",
            ]
        else:
            out += [
                "| RPC | Request | Response | Stream | What it does |",
                "|---|---|---|---|---|",
            ]
        for rpc in rpcs:
            key = (service, rpc["name"])
            name = f"`{rpc['name']}`" + (" *(deprecated)*" if rpc["deprecated"] else "")
            what = summaries.get(key) or summary(rpc["comment"])
            common = f"`{rpc['request']}` | `{rpc['response']}` | {rpc['streaming']} |"
            if host:
                out.append(
                    f"| {name} | {code(permissions.get(rpc['name'], ''))} | {common} "
                    f"{routing.get(key, '—')} | {cell(what)} |"
                )
            elif service == "PluginCapabilityService":
                out.append(
                    f"| {name} | {code(capabilities.get(key, ''))} | {common} "
                    f"{routing.get(key, '—')} | {cell(what)} |"
                )
            else:
                out.append(f"| {name} | {common} {cell(summary(rpc['comment']))} |")
        out.append("")
        if host:
            out += [
                "`none` means every plugin may always call it — the bootstrap set, which "
                "the daemon does not run a permission check on at all. It is a claim about "
                "the daemon, not a shrug: the column comes from "
                "[`spec/hooks.yaml`](../../../spec/hooks.yaml), and parity rule R6 checks "
                "every row of it against `HOST_RPC_PERMISSIONS` in the daemon's "
                "`plugins/host_service.rs`, which is the table `require_permission` reads. "
                "A host RPC with no row there is ungated, and R6 calls that a security "
                "finding rather than a spec typo.",
                "",
                "The gate answers at the *start* of a call. `SubscribeEvents` starts once "
                "and runs until the plugin exits, so the daemon ends the stream — with "
                "`permission_denied` and a teardown-reason trailer — when a grant is "
                "narrowed, consent is declined or the plugin is revoked. A withdrawn "
                "permission is therefore distinguishable from a dropped connection.",
                "",
            ]

    other = [s for s in services if s not in ("PluginCapabilityService", "PluginHostService", "PluginService")]
    out += [
        "## The rest of the slice",
        "",
        "The plugin proto carries Astra's own client-facing services too, because a "
        "`client` plugin — one that puts a chat surface somewhere Astra is not, like the "
        "Telegram example — drives the daemon through them with the SDK's `Daemon` handle. "
        "They are not plugin hooks and no capability implies them.",
        "",
        "| Service | RPCs |",
        "|---|---|",
    ]
    for service in other:
        out.append(f"| `{service}` | {len(services[service])} |")
    out += [
        "",
        "Full signatures are in [`proto/plugin.proto`](../../../proto/plugin.proto); this "
        "page does not restate 100-odd RPCs a plugin reaches only through the SDK's typed "
        "wrapper.",
        "",
        "## Deprecations",
        "",
    ]
    deprecated = [
        (service, rpc)
        for service, rpcs in services.items()
        for rpc in rpcs
        if rpc["deprecated"]
    ]
    if deprecated:
        out += ["| RPC | Why |", "|---|---|"]
        for service, rpc in deprecated:
            out.append(f"| `{service}.{rpc['name']}` | {cell(summary(rpc['comment']))} |")
    else:
        out.append("None: no RPC in this slice carries `option deprecated = true`.")
    out += [
        "",
        "A deprecated RPC stays declared. Removing it would break the generated trait "
        "implementations every SDK emits, and a plugin that dials one should keep getting "
        "`UNIMPLEMENTED` — which means *absent* — rather than a transport error.",
        "",
    ]
    return "\n".join(out).rstrip() + "\n"
