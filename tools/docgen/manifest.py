"""`docs/en/reference/manifest.md` — `plugin.toml`, from the crate that parses it.

# One definition, and this page is a third reader of it

`astra-plugin-manifest` is the single definition of a plugin manifest: the
daemon parses `plugin.toml` with it, `astra-plugin check` validates with it, and
the registry bot ingests with it. The crate exists because there used to be two
structs — the CLI's fork grew a `ui_panels` capability the daemon never had,
serde dropped the unknown key, and three shipped examples declared no
capabilities at all with no error anywhere.

The old `docs/en/manifest.md` was the third fork. It documented a manifest that
was missing `homepage`, `min_astra_version`, `call_timeout_secs`, `entry.cwd`,
`[dependencies]`, `[platform]`, `[build]` and `[ui]`, and it told authors that
unknown sections are ignored — which is true of the manifest and emphatically
false of `[capabilities]`, where an unknown key fails the whole parse.

So the page is derived from the crate:

  * **sections** — the fields of `PluginManifest`, in declaration order;
  * **fields** — each section struct's fields, their Rust types, whether serde
    fills them in when absent, and the literal a `#[serde(default = "fn")]`
    returns;
  * **what rejects it** — the `bail!`/`ensure!` sites in `PluginManifest::
    validate` and the two `min_astra_version` helpers, condition and message;
  * **vocabularies** — `CAPABILITY_NAMES`, `PERMISSION_NAMES`,
    `HIGH_RISK_PERMISSIONS`, `TIER2_REFUSED_PERMISSIONS`, `KNOWN_OS_VALUES`,
    `KNOWN_ARCH_VALUES`, `RESERVED_PLATFORM_KEYS`, each with the doc comment the
    crate keeps on it.

The vendored copy under `astra-plugin-cli/vendor/` is read rather than Astra's,
because that copy is what this repository ships and `tools/check-manifest-crate.sh`
already fails CI when it differs from Astra's byte for byte.

# The join with `spec/hooks.yaml`

Two columns cannot come from the crate, because the crate deliberately knows
nothing about the daemon: which hooks a capability obliges you to implement, and
which host RPC a permission unlocks. Both come from `spec/hooks.yaml`, whose
`permission` column parity rule R6 pins to the daemon's own
`HOST_RPC_PERMISSIONS`. Named on the page, so a reader knows which claims are
about the manifest and which are about the daemon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import rustsrc
from common import DocgenError, banner, cell, code, paragraphs, read

CRATE = "astra-plugin-cli/vendor/astra-plugin-manifest"
SRC = {
    "manifest": f"{CRATE}/src/manifest.rs",
    "capabilities": f"{CRATE}/src/capabilities.rs",
    "permissions": f"{CRATE}/src/permissions.rs",
    "platform": f"{CRATE}/src/platform.rs",
}

#: Rust type -> what an author writes in TOML.
TOML_TYPES = {
    "String": "string",
    "bool": "boolean",
    "i32": "integer",
    "u32": "integer",
    "u64": "integer",
    "Option<u64>": "integer",
    "Vec<String>": "array of strings",
    "HashMap<String, String>": "table of strings",
    "Capabilities": "table",
    "Permissions": "table",
    "PlatformRequirements": "table",
    "Option<ConfigSection>": "table",
    "Option<BuildSection>": "table",
    "Option<UiSection>": "table",
    "PluginMeta": "table",
    "EntryConfig": "table",
    "Vec<UiContributionDef>": "array of tables",
}


def toml_type(ty: str) -> str:
    plain = " ".join(ty.split())
    if plain in TOML_TYPES:
        return TOML_TYPES[plain]
    raise DocgenError(
        f"{CRATE}: no TOML spelling for the Rust type `{plain}`. Add it to TOML_TYPES in "
        f"tools/docgen/manifest.py — a field whose type the reference cannot name is a "
        f"field an author cannot write."
    )


def first_sentence(doc: str) -> str:
    doc = " ".join(doc.split())
    if not doc:
        return ""
    match = re.search(r"^(.+?[.!?])(\s|$)", doc)
    return match.group(1) if match else doc


@dataclass
class Section:
    key: str
    struct: str
    required: bool
    doc: str


def _sources() -> dict[str, str]:
    return {name: read(path) for name, path in SRC.items()}


def _default_note(f: rustsrc.Field, text: str) -> str:
    if f.ty.startswith("Option<"):
        return "absent"
    fn = f.default_fn
    if fn:
        literal = rustsrc.fn_literal(text, fn)
        if literal is None:
            raise DocgenError(
                f"{SRC['manifest']}: `#[serde(default = \"{fn}\")]` on `{f.name}`, and no "
                f"`fn {fn}()` this reader can read a literal out of. The reference would "
                f"have to guess the default."
            )
        return f"`{literal}`"
    if f.has_serde("default"):
        return {
            "String": '`""`',
            "bool": "`false`",
            "i32": "`0`",
            "u32": "`0`",
            "u64": "`0`",
        }.get(f.ty, "empty")
    return "—"


def _field_table(
    struct: rustsrc.Item, text: str, prefix: str, refused: set[str] | None = None
) -> list[str]:
    out = [
        "| Key | Type | Required | Default | What it is |",
        "|---|---|---|---|---|",
    ]
    refused = refused or set()
    marked = False
    notes: list[tuple[str, str]] = []
    for f in struct.fields:
        required = "no" if f.optional else "**yes**"
        summary = first_sentence(f.doc) or "—"
        key = f"`{f.name}`"
        if f"{prefix}.{f.name}" in refused:
            key += " [†](#what-is-refused)"
            marked = True
        out.append(
            f"| {key} | {toml_type(f.ty)} | {required} | {_default_note(f, text)} | "
            f"{cell(summary)} |"
        )
        rest = " ".join(f.doc.split())
        if rest and rest != summary:
            notes.append((f"{prefix}.{f.name}", f.doc))
    out.append("")
    if marked:
        out += [
            "† has a rule that refuses the manifest outright — see "
            "[what is refused](#what-is-refused) for the condition and the message.",
            "",
        ]
    for name, doc in notes:
        out += [f"**`{name}`.** {paragraphs(doc)}", ""]
    return out


def _rejections(text: str) -> list[tuple[str, str]]:
    """Every refusal `PluginManifest::validate` and its helpers can produce.

    Condition and message both come out of the source. The conditions are Rust
    expressions and are shown as such: paraphrasing them is how a reference
    starts saying something subtly different from the code, and the whole
    reason `plugin.id` has a charset rule is that it becomes a directory name.
    """
    rules: list[tuple[str, str]] = []
    # Tests carry deliberately-invalid manifests; only the crate's own code is
    # a statement about what a manifest may be.
    body = text.partition("#[cfg(test)]")[0]
    lines = body.split("\n")
    starts = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1

    def line_of(index: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= index:
                lo = mid
            else:
                hi = mid - 1
        return lo

    for match in re.finditer(r"anyhow::bail!\(", body):
        i = line_of(match.start())
        condition = None
        for j in range(i - 1, max(i - 12, -1), -1):
            if lines[j].strip().startswith("if "):
                condition = " ".join(" ".join(lines[k].strip() for k in range(j, i)).split())
                break
        if condition is None:
            continue
        quote = body.index('"', match.end())
        message = _string_at(body, quote)
        if message:
            rules.append((_tidy(condition.removeprefix("if ").rstrip("{")), message))

    for match in re.finditer(r"anyhow::ensure!\(\s*([^,]+),\s*\n?\s*\"", body):
        message = _string_at(body, match.end() - 1)
        if message:
            rules.append((f"not ({_tidy(match.group(1))})", message))

    # A fallible call annotated with `.with_context`. Kept only when the message
    # names a manifest key: `from_file`'s "Failed to read {}" is an I/O failure,
    # not a statement about what a manifest may contain.
    for match in re.finditer(
        r"([\w:]+\([^()]*\))\s*\.with_context\(\|\|\s*\{?\s*format!\(\s*\"", body
    ):
        message = _string_at(body, match.end() - 1)
        if message and re.search(r"\b(plugin|entry|config|build|ui|platform)\.\w+", message):
            rules.append((f"`{_tidy(match.group(1))}` returns Err", message))

    if len(rules) < 8:
        raise DocgenError(
            f"{SRC['manifest']}: found only {len(rules)} rejection rule(s). `validate()` has "
            f"had seven `bail!`s plus the two `min_astra_version` refusals since Phase 0; "
            f"finding fewer means this reader stopped matching the source and the page would "
            f"under-report what a manifest is refused for."
        )
    return rules


def _string_at(text: str, quote_index: int) -> str:
    """The Rust string literal whose opening quote is at `quote_index`."""
    out = []
    i = quote_index + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            nxt = text[i + 1]
            if nxt == "\n":
                # Rust's line continuation: the newline and the following
                # indentation are not part of the string.
                i += 2
                while i < len(text) and text[i] in " \t":
                    i += 1
                continue
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def refused_keys(text: str) -> set[str]:
    """Dotted manifest keys named in a refusal message.

    `plugin.id is required` names `plugin.id`. Read out of the messages rather
    than out of the conditions, because a message is what an author is shown
    and is therefore the thing that must agree with the table above it.
    """
    keys: set[str] = set()
    for _, message in _rejections(text):
        keys.update(re.findall(r"\b(?:plugin|entry|config|build|ui|platform)\.\w+", message))
    return keys


def _tidy(expression: str) -> str:
    """One line of Rust, from an expression that was wrapped across several."""
    return re.sub(r"\s+\.", ".", " ".join(expression.split())).strip()


def _hooks():
    """`spec/hooks.yaml`, for the capability and permission joins."""
    import parity

    _, spec = parity._load()
    return spec.load()


def render() -> str:
    src = _sources()
    manifest_src = src["manifest"]
    doc = _hooks()

    root = rustsrc.item(manifest_src, "struct", "PluginManifest")
    if root is None or not root.fields:
        raise DocgenError(f"{SRC['manifest']}: `struct PluginManifest` not found.")

    structs: dict[str, rustsrc.Item] = {}
    for text in src.values():
        for struct in (
            "PluginMeta",
            "EntryConfig",
            "ConfigSection",
            "BuildSection",
            "UiSection",
            "UiContributionDef",
            "Capabilities",
            "Permissions",
            "PermissionRequest",
            "PlatformRequirements",
        ):
            found = rustsrc.item(text, "struct", struct)
            if found is not None:
                structs[struct] = found

    out = [
        banner(
            "manifest.py",
            [f"{path} — the crate the daemon parses `plugin.toml` with" for path in SRC.values()]
            + ["spec/hooks.yaml — the capability and permission joins (see below)"],
        ),
        "# `plugin.toml` reference",
        "",
        "Every section, every key, and everything that refuses one. Derived from "
        f"[`astra-plugin-manifest`](../../../{CRATE}/src/manifest.rs) — the crate the daemon "
        "parses your manifest with, vendored into this repository and held byte-identical to "
        "Astra's copy by `tools/check-manifest-crate.sh`. There is no second definition of a "
        "manifest to disagree with this page.",
        "",
        paragraphs(root.doc),
        "",
        "## Sections",
        "",
        "| Section | Required | What it declares |",
        "|---|---|---|",
    ]

    sections: list[Section] = []
    for f in root.fields:
        sections.append(
            Section(
                key=f.name,
                struct=re.sub(r"^Option<(.+)>$", r"\1", f.ty),
                required=not f.optional,
                doc=f.doc,
            )
        )
    for section in sections:
        summary = (
            first_sentence(section.doc)
            or _struct_summary(structs, section.struct)
            or f"A {toml_type(section.struct)}, with no schema of its own."
        )
        out.append(
            f"| [`[{section.key}]`](#{section.key}) | "
            f"{'**yes**' if section.required else 'no'} | {cell(summary)} |"
        )
    out += [
        "",
        "A section this Astra does not know is **kept, not refused** — sections are added "
        "over releases and an older daemon has to be able to skip one. `[capabilities]` is "
        "the single exception and the reason is below.",
        "",
    ]

    refused = refused_keys(manifest_src)
    for section in sections:
        out += _render_section(section, structs, src, doc, refused)

    out += _render_rejections(manifest_src)
    return "\n".join(out).rstrip() + "\n"


def _struct_summary(structs: dict[str, rustsrc.Item], name: str) -> str:
    item = structs.get(name)
    return first_sentence(item.doc) if item else ""


def _render_section(
    section: Section,
    structs: dict[str, rustsrc.Item],
    src: dict[str, str],
    doc: dict,
    refused: set[str],
) -> list[str]:
    out = [f"## `[{section.key}]`", ""]
    if section.doc:
        out += [paragraphs(section.doc), ""]

    if section.key == "capabilities":
        return out + _render_capabilities(structs, src, doc)
    if section.key == "permissions":
        return out + _render_permissions(structs, src, doc)
    if section.key == "platform":
        return out + _render_platform(structs, src)
    if section.key == "dependencies":
        return out + [
            "A free table of `name = \"version requirement\"`. Both halves are strings and "
            "the crate reads them as such — `HashMap<String, String>`, no schema, no "
            "resolution, and nothing installs anything from it. `astra-plugin check` lists "
            "what is declared and warns when a requirement is empty; that is the whole of "
            "its effect.",
            "",
        ]

    struct = structs.get(section.struct)
    if struct is None:
        raise DocgenError(
            f"{SRC['manifest']}: `[{section.key}]` is `{section.struct}`, which docgen could "
            f"not find. The struct moved or was renamed."
        )
    if struct.doc and struct.doc != section.doc:
        out += [paragraphs(struct.doc), ""]
    out += _field_table(struct, src["manifest"], section.key, refused)

    if section.key == "ui":
        contribution = structs["UiContributionDef"]
        out += ["### `[[ui.contributions]]`", ""]
        if contribution.doc:
            out += [paragraphs(contribution.doc), ""]
        out += _field_table(contribution, src["manifest"], "ui.contributions")
    return out


def _render_capabilities(
    structs: dict[str, rustsrc.Item], src: dict[str, str], doc: dict
) -> list[str]:
    text = src["capabilities"]
    names = rustsrc.const_list(text, "CAPABILITY_NAMES")
    struct = structs["Capabilities"]
    if not names:
        raise DocgenError(f"{SRC['capabilities']}: CAPABILITY_NAMES not found.")
    fields = [f.name for f in struct.fields]
    if fields != names:
        raise DocgenError(
            f"{SRC['capabilities']}: CAPABILITY_NAMES {names} and the fields of "
            f"`Capabilities` {fields} disagree. The crate's own test asserts they do not; "
            f"one of the two readers is broken."
        )

    deny = any("deny_unknown_fields" in attr for attr in struct.attrs)
    out = []
    if deny:
        out += [
            "**An unknown key here fails the whole manifest.** `Capabilities` is "
            "`#[serde(deny_unknown_fields)]`, alone among the sections: it is entirely "
            "opt-in booleans, so a typo would otherwise read exactly like `false` and the "
            "plugin would install having declared nothing. That is not hypothetical — three "
            "shipped examples declared `ui_panels`, a name no daemon has ever had, and the "
            "only symptom was `astra-plugin check` printing \"No capabilities enabled\".",
            "",
        ]
    else:
        raise DocgenError(
            f"{SRC['capabilities']}: `Capabilities` is no longer `deny_unknown_fields`. "
            f"That attribute is the reason this section behaves differently from every "
            f"other one, and the page says so — verify the change before regenerating."
        )

    out += [
        "Every key is a boolean and defaults to `false`. The right-hand column is the "
        "join with [`spec/hooks.yaml`](../../../spec/hooks.yaml): the hooks your plugin "
        "must serve for the capability to work at all. `optional` hooks are omitted here; "
        "[`parity.md`](./parity.md) has all of them.",
        "",
        "| Key | Hooks it obliges you to implement |",
        "|---|---|",
    ]
    for name in names:
        required = [
            h["rpc"]
            for h in doc["hooks"]
            if h["capability"] == name
            and h["requirement"] == "required"
            and h["routing"] == "live"
        ]
        cellv = ", ".join(f"`{r}`" for r in required) if required else "none"
        out.append(f"| `{name}` | {cellv} |")
    out.append("")

    renamed = re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', text.partition("RENAMED_CAPABILITIES")[2])
    if renamed:
        out += ["**Names that were never real:**", ""]
        for old, new in renamed:
            out.append(f"- `{old}` → `{new}`")
        out.append("")
    return out


def _render_permissions(
    structs: dict[str, rustsrc.Item], src: dict[str, str], doc: dict
) -> list[str]:
    text = src["permissions"]
    names = rustsrc.const_list(text, "PERMISSION_NAMES")
    enum = rustsrc.item(text, "enum", "Permission")
    if not names or enum is None:
        raise DocgenError(f"{SRC['permissions']}: PERMISSION_NAMES or `enum Permission` not found.")
    ids = rustsrc.match_arms(text, "id")
    high_risk = rustsrc.const_list(text, "HIGH_RISK_PERMISSIONS") or []
    tier2 = rustsrc.const_list(text, "TIER2_REFUSED_PERMISSIONS") or []
    if not high_risk or not tier2:
        raise DocgenError(
            f"{SRC['permissions']}: HIGH_RISK_PERMISSIONS / TIER2_REFUSED_PERMISSIONS not found."
        )

    gates = {
        h["permission"]: h["rpc"]
        for h in doc["hooks"]
        if h["service"] == "PluginHostService" and h.get("permission", "none") != "none"
    }

    out = [
        "Each key is a permission id and each value is a table.",
        "",
        "An id this Astra does not know is kept and inert: forward compatibility, and "
        "`permissions_hash` is computed over these bytes by three implementations, so a "
        "reader that dropped an unrecognised key would disagree with the other two about "
        "what was signed.",
        "",
        "| Id | Gates | Own consent checkbox | Refused to a local import | What it grants |",
        "|---|---|---|---|---|",
    ]
    for variant in enum.fields:
        wire = ids.get(variant.name)
        if wire is None:
            raise DocgenError(
                f"{SRC['permissions']}: `Permission::{variant.name}` has no arm in `fn id`."
            )
        out.append(
            f"| `{wire}` | {code(gates.get(wire, ''))} | "
            f"{'**yes**' if variant.name in high_risk else 'no'} | "
            f"{'**yes**' if variant.name in tier2 else 'no'} | "
            f"{cell(_permission_summary(variant.doc))} |"
        )
    out += [
        "",
        "*Gates* is the host RPC the daemon refuses without the permission, from "
        "[`spec/hooks.yaml`](../../../spec/hooks.yaml); parity rule R6 checks that column "
        "against the daemon's own `HOST_RPC_PERMISSIONS`, the table `require_permission` "
        "reads. An empty cell is a **surface** permission that gates no RPC: `dom_access` "
        "decides how a UI contribution is rendered, and `client` is a capability ceiling.",
        "",
        "*Refused to a local import* is the ceiling on a `.astraplugin` file the user "
        "imported by hand rather than installed from the store: those ids are dropped "
        "outright, not warned about. A source directory loaded with Developer Mode on is "
        "deliberately not capped — it is the authoring loop for UI plugins.",
        "",
    ]

    request = structs["PermissionRequest"]
    out += ["### The value of a permission key", ""]
    out += _field_table(request, text, "<permission>")

    for variant in enum.fields:
        wire = ids[variant.name]
        rest = " ".join(variant.doc.split())
        if rest and rest != _permission_summary(variant.doc):
            out += [f"**`{wire}`.** {paragraphs(variant.doc)}", ""]
    return out


def _permission_summary(doc: str) -> str:
    """A variant's doc, minus the leading `Service.Rpc —` it usually opens with.

    The RPC is already its own column, and repeating it there would push the
    sentence that says what the permission *grants* off the end of the row.
    """
    text = re.sub(r"^`[\w.]+`\s*[—-]\s*", "", first_sentence(doc))
    return text[:1].upper() + text[1:] if text else text


def _render_platform(structs: dict[str, rustsrc.Item], src: dict[str, str]) -> list[str]:
    text = src["platform"]
    struct = structs["PlatformRequirements"]
    out = _field_table(struct, text, "platform")
    for const in ("KNOWN_OS_VALUES", "KNOWN_ARCH_VALUES", "RESERVED_PLATFORM_KEYS"):
        values = rustsrc.const_list(text, const)
        if not values:
            raise DocgenError(f"{SRC['platform']}: `{const}` not found.")
        doc = rustsrc.const_doc(text, const)
        out += [
            f"**`{const}`** — {', '.join(f'`{v}`' for v in values)}",
            "",
        ]
        if doc:
            out += [paragraphs(doc), ""]
    return out


def _render_rejections(text: str) -> list[str]:
    out = [
        "## What is refused",
        "",
        "Every refusal `PluginManifest::validate` can produce, with the condition that "
        "triggers it. Conditions are the Rust expressions themselves: `plugin.id` becomes "
        "a path component — `<plugins_dir>/<id>/`, created and later `remove_dir_all`'d — "
        "so paraphrasing the charset rule is not a thing this page is willing to do.",
        "",
        "| The manifest is refused when | The message |",
        "|---|---|",
    ]
    for condition, message in _rejections(text):
        out.append(f"| `{cell(condition)}` | {cell(message)} |")
    out += [
        "",
        "`min_astra_version` is the one rule with two halves. Its **syntax** is checked "
        "everywhere, including in `astra-plugin check`: a value that is not a semver "
        "version is a declared constraint that constrains nothing. Its **value** is "
        "compared only in a build that is itself an Astra — a tool refusing to look at a "
        "plugin because it targets a newer daemon than the tool would be nonsense.",
        "",
    ]
    return out
