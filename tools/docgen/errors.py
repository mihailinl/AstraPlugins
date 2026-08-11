"""`docs/en/reference/errors.md` — the error taxonomy, from four sources at once.

The eight codes are the one part of this protocol that has to be *identical* in
four places and is written out longhand in all four: the `PluginErrorCode` enum
in the proto, `ToolError`/`ToolErrorCode` in the Rust SDK, `ErrorCode` and its
exception classes in Python, and the string union with its classes in
TypeScript. Nothing links them at compile time across languages.

So this generator reads all four and *joins* them. A code present in three and
missing from one, or mapped to a different gRPC status in one, fails generation
before it can become a page that quietly documents one SDK's version of the
truth. That check is the reason this page is generated rather than written: the
table is trivial to write and impossible to keep true by hand.

# The two channels

A `ToolError` is **in-band**: it travels in the response message, because a tool
that failed has produced a result the model must read — "you have not set an API
key" is an answer, not a transport fault. gRPC `Status` is reserved for the call
not reaching the handler, and `UNIMPLEMENTED` specifically means *this plugin
does not have that hook*. The transport column below is the fixed mapping used
by the hooks whose response message has no in-band error field.
"""

from __future__ import annotations

import re

import rustsrc
from common import DocgenError, banner, cell, paragraphs, read

PROTO = "proto/plugin.proto"
RUST = "astra-plugin-sdk/src/error.rs"
PYTHON = "astra-plugin-sdk-python/astra_plugin_sdk/errors.py"
TS = "astra-plugin-sdk-ts/src/errors.ts"


def screaming(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).upper()


def proto_codes() -> list[tuple[str, int, str]]:
    """`(variant, number, comment)` for every `PluginErrorCode` value."""
    text = read(PROTO)
    match = re.search(r"enum\s+PluginErrorCode\s*\{(.*?)\n\}", text, re.DOTALL)
    if not match:
        raise DocgenError(f"{PROTO}: `enum PluginErrorCode` not found.")
    body = match.group(1)
    out: list[tuple[str, int, str]] = []
    comment: list[str] = []
    # A `── Per-call failures ──` block documents the group, not the next
    # variant. It runs until the blank line that ends the comment, so the whole
    # block is skipped rather than only its first line.
    in_banner = False
    for raw in body.split("\n"):
        line = raw.strip()
        if line.startswith("//"):
            body_text = line.removeprefix("//").strip()
            if body_text.startswith("──"):
                in_banner, comment = True, []
                continue
            if in_banner:
                continue
            comment.append(body_text)
            continue
        value = re.match(r"^(\w+)\s*=\s*(\d+)\s*;", line)
        if value:
            out.append((value.group(1), int(value.group(2)), " ".join(" ".join(comment).split())))
            comment = []
            continue
        if not line:
            in_banner = False
            continue
        comment = []
    if len(out) < 12:
        raise DocgenError(
            f"{PROTO}: parsed {len(out)} PluginErrorCode values; the enum has had twelve "
            f"(0 unspecified, 1-3 registration, 4-11 per-call) since Phase 5."
        )
    return out


def rust_facts() -> dict:
    text = read(RUST)
    enum = rustsrc.item(text, "enum", "ToolErrorCode")
    if enum is None or not enum.fields:
        raise DocgenError(f"{RUST}: `enum ToolErrorCode` not found.")
    wire = rustsrc.match_arms(text, "as_str")
    if len(wire) != len(enum.fields):
        raise DocgenError(
            f"{RUST}: `ToolErrorCode::as_str` has {len(wire)} arms for "
            f"{len(enum.fields)} variants."
        )

    tool_error = re.search(r"pub enum ToolError\s*\{(.*?)\n\}", text, re.DOTALL)
    if not tool_error:
        raise DocgenError(f"{RUST}: `pub enum ToolError` not found.")
    tool_variants = re.findall(r"^\s{4}([A-Z]\w*)\s*[({,]", tool_error.group(1), re.MULTILINE)
    if not tool_variants:
        raise DocgenError(f"{RUST}: `ToolError` parsed with no variants.")

    status = dict(re.findall(r"ToolErrorCode::(\w+)\s*=>\s*Code::(\w+)", text))
    if len(status) != len(enum.fields):
        raise DocgenError(f"{RUST}: `to_status` covers {len(status)} of {len(enum.fields)} codes.")

    return {
        "codes": {wire[v.name]: v.name for v in enum.fields},
        "variants": tool_variants,
        "extra": [v for v in tool_variants if v not in {f.name for f in enum.fields}],
        "status": {wire[k]: screaming(v) for k, v in status.items()},
    }


def python_facts() -> dict:
    text = read(PYTHON)
    enum = re.search(r"class ErrorCode\(str, enum\.Enum\):(.*?)\n\n\n", text, re.DOTALL)
    if not enum:
        raise DocgenError(f"{PYTHON}: `class ErrorCode` not found.")
    codes = dict(re.findall(r"^\s{4}(\w+)\s*=\s*\"(\w+)\"", enum.group(1), re.MULTILINE))
    classes = dict(
        (code, name)
        for name, code in re.findall(
            r"class (\w+)\(PluginError\):.*?\n\s*code\s*=\s*ErrorCode\.(\w+)", text, re.DOTALL
        )
    )
    status = dict(
        re.findall(r"ErrorCode\.(\w+):\s*grpc\.StatusCode\.(\w+)", text)
    )
    if not codes or not classes or not status:
        raise DocgenError(f"{PYTHON}: codes/classes/status map — one of the three parsed empty.")
    # Keyed by the WIRE value throughout, so the join in `render` compares the
    # same strings the three SDKs put on the wire rather than three languages'
    # spellings of an identifier.
    return {
        "codes": {codes[k]: k for k in codes},
        "classes": {codes[k]: v for k, v in classes.items()},
        "status": {codes[k]: v for k, v in status.items()},
    }


def ts_facts() -> dict:
    text = read(TS)
    union = re.search(r"export type PluginErrorCode =(.*?);", text, re.DOTALL)
    if not union:
        raise DocgenError(f"{TS}: `export type PluginErrorCode` not found.")
    codes = re.findall(r'"(\w+)"', union.group(1))
    classes = dict(
        (code, name)
        for name, code in re.findall(
            r"export class (\w+) extends PluginError \{\s*readonly code = \"(\w+)\"", text
        )
    )
    status = dict(re.findall(r"^\s{2}(\w+):\s*grpc\.status\.(\w+),", text, re.MULTILINE))
    if not codes or not classes or not status:
        raise DocgenError(f"{TS}: codes/classes/status map — one of the three parsed empty.")
    return {"codes": codes, "classes": classes, "status": status}


def render() -> str:
    proto = proto_codes()
    rust = rust_facts()
    python = python_facts()
    ts = ts_facts()

    codes = list(rust["codes"])  # declaration order of ToolErrorCode
    problems = []
    for name, source in (("Python", python["codes"]), ("TypeScript", set(ts["codes"]))):
        missing = [c for c in codes if c not in source]
        extra = [c for c in source if c not in codes]
        if missing or extra:
            problems.append(f"{name}: missing {missing or '—'}, extra {extra or '—'}")
    proto_names = {v for v, _, _ in proto}
    for c in codes:
        if not any(v.endswith(c) for v in proto_names):
            problems.append(f"{PROTO} has no PluginErrorCode variant ending in {c}")
    for c in codes:
        mappings = {rust["status"].get(c), python["status"].get(c), ts["status"].get(c)}
        if len(mappings) != 1 or None in mappings:
            problems.append(
                f"{c} maps to different gRPC statuses: rust={rust['status'].get(c)}, "
                f"python={python['status'].get(c)}, ts={ts['status'].get(c)}"
            )
    for c in codes:
        if c not in python["classes"] or c not in ts["classes"]:
            problems.append(f"{c} has no exception class in Python and/or TypeScript")
    if problems:
        raise DocgenError(
            "the four error taxonomies disagree. Nothing links them at compile time "
            "across languages, which is why this is checked here:\n  " + "\n  ".join(problems)
        )

    by_variant = {v: (n, c) for v, n, c in proto}
    out = [
        banner(
            "errors.py",
            [
                f"{PROTO} — `enum PluginErrorCode`",
                f"{RUST} — `ToolError`, `ToolErrorCode`, `to_status`",
                f"{PYTHON} — `ErrorCode`, the exception classes, `_GRPC_STATUS`",
                f"{TS} — `PluginErrorCode`, the exception classes, `GRPC_STATUS`",
            ],
            extra=[
                "The four are joined and cross-checked: a code missing from one, or mapped",
                "to a different gRPC status in one, fails generation.",
            ],
        ),
        "# Error reference",
        "",
        "One taxonomy, four implementations, and this page is the join. The eight per-call "
        "codes are spelled out longhand in the proto and in each of the three SDKs, and "
        "nothing links them across languages at compile time — so they are compared here, "
        "and a disagreement fails the build rather than becoming a page that documents one "
        "SDK's version of the truth.",
        "",
        "## The two channels",
        "",
        "**In-band — the error the caller reads.** A tool that failed has produced a "
        "result. `NOT_CONFIGURED: OpenAI API key is not set` is what the model has to see "
        "to tell the user what to do, and what the UI turns into a link to that exact "
        "settings field. It travels inside the response message.",
        "",
        "**Transport — gRPC `Status`.** Reserved for the call never reaching the handler: "
        "no such hook, not authenticated, connection gone. `UNIMPLEMENTED` means *this "
        "plugin does not have that hook*, which is a claim about the plugin's shape and not "
        "about this call — the daemon reads it as \"hook absent\" and carries on. Returning "
        "a transport error for a per-call failure throws that distinction away and, for a "
        "tool, loses the model's answer.",
        "",
        "The transport column below is the fixed mapping, used by the hooks whose response "
        "message has no in-band error field (TTS, STT, AI). It is a bijection: a plugin "
        "forwarding a gRPC failure gets the same code back that it put in.",
        "",
        "## The eight per-call codes",
        "",
        "| Code | Proto | Rust | Python | TypeScript | Transport |",
        "|---|---|---|---|---|---|",
    ]
    for c in codes:
        variant = next(v for v in proto_names if v.endswith(c))
        number, _ = by_variant[variant]
        rust_variant = rust["codes"][c]
        out.append(
            f"| `{c}` | `{variant}` = {number} | `ToolError::{rust_variant}` | "
            f"`{python['classes'][c]}` | `{ts['classes'][c]}` | "
            f"`{rust['status'][c]}` |"
        )
    out.append("")

    for extra in rust["extra"]:
        out += [
            f"### `ToolError::{extra}` — a variant with no code of its own",
            "",
            paragraphs(_variant_doc(read(RUST), extra)),
            "",
        ]

    out += ["### What each one means", ""]
    for c in codes:
        variant = next(v for v in proto_names if v.endswith(c))
        _, comment = by_variant[variant]
        if comment:
            out += [f"**`{c}`.** {paragraphs(comment)}", ""]

    out += [
        "## Registration refusals",
        "",
        "The same enum carries the codes a daemon answers `Register` with. A plugin never "
        "produces one; it receives one, and then exits.",
        "",
        "| Code | Number | What it means |",
        "|---|---|---|",
    ]
    for variant, number, comment in proto:
        if number == 0 or any(variant.endswith(c) for c in codes):
            continue
        out.append(f"| `{variant}` | {number} | {cell(comment or '—')} |")
    out += [
        "",
        "`PLUGIN_ERROR_UNSPECIFIED = 0` is proto3's zero value and means the sender set "
        "nothing.",
        "",
        "## The fields an error carries",
        "",
    ]

    detail = _detail_fields()
    out += ["| Field | For | What it is |", "|---|---|---|"]
    for name, meaning in detail:
        out.append(f"| `{name}` | {meaning[0]} | {cell(meaning[1])} |")
    out += [
        "",
        "Both halves are always sent. The structured message is an addition, not a "
        "replacement: a plugin built against an older protocol sends no structured detail, "
        "and one built against this protocol talking to an older daemon has it dropped by "
        "the receiver's parser. In both directions the human string survives, so both "
        "pairings keep working — which is also why the string is prefixed with the code "
        "(`NOT_CONFIGURED: …`): that prefix is what tells the AI loop to stop retrying.",
        "",
        "## Absent hooks are not errors",
        "",
        _hook_absence(),
        "",
    ]
    return "\n".join(out).rstrip() + "\n"


def _detail_fields() -> list[tuple[str, tuple[str, str]]]:
    """The fields of the proto's `PluginError` message, with their comments."""
    text = read(PROTO)
    match = re.search(r"message PluginError \{(.*?)\n\}", text, re.DOTALL)
    if not match:
        raise DocgenError(f"{PROTO}: `message PluginError` not found.")
    body = match.group(1)
    out = []
    comment: list[str] = []
    for raw in body.split("\n"):
        line = raw.strip()
        if line.startswith("//"):
            comment.append(line.removeprefix("//").strip())
            continue
        field = re.match(r"^([\w.]+)\s+(\w+)\s*=\s*\d+;\s*(?://\s*(.*))?$", line)
        if field:
            text_comment = " ".join(" ".join(comment).split()) or (field.group(3) or "")
            if not text_comment and field.group(1) == "PluginErrorCode":
                text_comment = "One of the codes above."
            first = re.match(r"^(.+?[.!?])(\s|$)", text_comment)
            out.append(
                (
                    field.group(2),
                    ("every code", first.group(1) if first else text_comment or "—"),
                )
            )
            comment = []
            continue
        if not line:
            continue
        comment = []
    if len(out) < 6:
        raise DocgenError(f"{PROTO}: `message PluginError` parsed {len(out)} fields, expected 6.")
    # Two fields are only meaningful with one code each; the proto says so and
    # this is where a reader needs it in one glance.
    meanings = {"config_field": "`NOT_CONFIGURED`", "retry_after_ms": "`RATE_LIMITED`"}
    return [(name, (meanings.get(name, meaning[0]), meaning[1])) for name, meaning in out]


def _variant_doc(text: str, name: str) -> str:
    """The `///` block above an enum variant, however the variant is shaped."""
    match = re.search(rf"^\s{{4}}{name}\s*[({{,]", text, re.MULTILINE)
    if not match:
        raise DocgenError(f"{RUST}: variant `{name}` not found while reading its doc.")
    lines: list[str] = []
    for line in reversed(text[: match.start()].rstrip("\n").split("\n")):
        stripped = line.strip()
        if stripped.startswith("///"):
            lines.insert(0, stripped.removeprefix("///").strip())
        else:
            break
    if not lines:
        raise DocgenError(f"{RUST}: `ToolError::{name}` has no doc comment to quote.")
    return "\n".join(lines)


def _hook_absence() -> str:
    """The `HookUnimplemented` doc comment, quoted from the Rust SDK."""
    text = read(RUST)
    item = rustsrc.item(text, "struct", "HookUnimplemented")
    if item is None or not item.doc:
        raise DocgenError(f"{RUST}: `struct HookUnimplemented` and its doc comment are the "
                          f"statement that UNIMPLEMENTED means absent, not broken.")
    return paragraphs(item.doc)
