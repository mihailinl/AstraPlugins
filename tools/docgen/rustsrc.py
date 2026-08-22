"""A very small reader for the Rust sources docgen derives pages from.

Not a Rust parser. It knows four shapes, and every one of them is a shape the
files it is pointed at actually use:

  * `#[derive(..., Deserialize)] pub struct Name { ... }` with `#[serde(...)]`
    attributes and `///` doc comments on the fields;
  * `pub enum Name { Variant, ... }`, likewise;
  * `pub const NAME: &[&str] = &["a", "b"];`,
    `pub const NAME: &[Type] = &[Type::A, Type::B];`, and an element that is a
    `pub const OTHER: &str = "…";` declared beside the list;
  * `fn name() -> T { <literal> }`, for serde's `default = "fn"`.

Text and not `syn` for the same reason `tools/parity/check.py` reads sources as
text: this repository's docs check runs on a bare Python with no Rust toolchain
and no third-party packages, and a check that needs an environment nobody has
is a check that gets skipped.

The safety property is not "the parser is correct for all Rust". It is that
every lookup here is *asked for by name* by a caller that knows the item exists,
and returns nothing only if the item moved — at which point the caller raises
and generation fails. There is no path where a silent parse failure produces a
page that merely omits something.

Nor one where it produces a page that states the wrong thing. That is the
narrower hazard and the one this reader was actually bitten by: see
`_const_element`, where an unrecognised token used to be passed through and put
a Rust identifier on the page in the place a value belongs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from common import DocgenError


@dataclass
class Field:
    name: str
    ty: str
    doc: str
    attrs: list[str] = field(default_factory=list)

    @property
    def optional(self) -> bool:
        """serde fills this in when the key is absent."""
        return self.has_serde("default") or self.ty.startswith("Option<")

    @property
    def default_fn(self) -> str | None:
        for attr in self.attrs:
            match = re.search(r'default\s*=\s*"([^"]+)"', attr)
            if match:
                return match.group(1)
        return None

    def has_serde(self, key: str) -> bool:
        return any(re.search(rf"serde\([^)]*\b{key}\b", attr) for attr in self.attrs)


@dataclass
class Item:
    name: str
    doc: str
    attrs: list[str]
    fields: list[Field]


def _dedent_doc(lines: list[str]) -> str:
    return "\n".join(line.removeprefix("///").strip() for line in lines).strip()


def _collect(body: str) -> list[Field]:
    """Fields (or enum variants) of one `{ ... }` body."""
    out: list[Field] = []
    docs: list[str] = []
    attrs: list[str] = []
    depth = 0
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("///"):
            docs.append(line)
            continue
        if line.startswith("#["):
            attrs.append(line)
            continue
        if line.startswith("//"):
            continue
        # A field whose type is itself a brace block (none today) would need
        # real balancing; count braces so one cannot be silently mis-split.
        depth += line.count("{") - line.count("}")
        line = re.sub(r"^pub(\([^)]*\))?\s+", "", line)
        match = re.match(r"^(\w+)\s*:\s*(.+?),?\s*$", line)
        if match and depth <= 0:
            out.append(
                Field(
                    name=match.group(1),
                    ty=match.group(2).rstrip(","),
                    doc=_dedent_doc(docs),
                    attrs=attrs,
                )
            )
            docs, attrs = [], []
            continue
        variant = re.match(r"^([A-Z]\w*)\s*,?\s*$", line)
        if variant and depth <= 0:
            out.append(Field(name=variant.group(1), ty="", doc=_dedent_doc(docs), attrs=attrs))
            docs, attrs = [], []
            continue
        docs, attrs = [], []
    return out


def _block(text: str, start: int) -> str:
    """The `{ ... }` starting at or after `start`, brace-balanced."""
    open_at = text.index("{", start)
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : i]
    raise ValueError("unbalanced braces")


def item(text: str, kind: str, name: str) -> Item | None:
    """One `struct`/`enum` by name, with its doc comment and attributes."""
    match = re.search(rf"^(pub )?{kind}\s+{name}\b", text, re.MULTILINE)
    if not match:
        return None
    head = text[: match.start()]
    doc_lines: list[str] = []
    attrs: list[str] = []
    for line in reversed(head.rstrip().split("\n")):
        stripped = line.strip()
        if stripped.startswith("#["):
            attrs.insert(0, stripped)
        elif stripped.startswith("///"):
            doc_lines.insert(0, stripped)
        elif stripped.startswith("//"):
            continue
        else:
            break
    return Item(
        name=name,
        doc=_dedent_doc(doc_lines),
        attrs=attrs,
        fields=_collect(_block(text, match.end())),
    )


def const_str(text: str, name: str) -> str | None:
    """`pub const NAME: &str = "value";` as its value."""
    match = re.search(rf"const\s+{name}\s*:\s*&\s*(?:'static\s+)?str\s*=\s*\"([^\"]*)\"", text)
    return match.group(1) if match else None


def _const_element(text: str, const_name: str, part: str) -> str:
    """One element of a `const NAME: &[...]`, as the VALUE it denotes.

    Three shapes, all of them shapes the sources use: a string literal; a path
    (`Type::Variant`), rendered as its last segment; and a bare identifier,
    which is a `&str` const declared beside the list and is resolved here to
    the string it holds.

    The third shape is in this reader because it arrived as a **wrong answer
    rather than a missing one**, which is the failure this whole directory is
    arranged against. `RESERVED_PLATFORM_KEYS` in `astra-plugin-manifest` held
    the literal `"noarch"` until Astra extracted it into `NOARCH_PLATFORM_KEY`;
    this function's predecessor stripped quotes and otherwise passed the token
    through, so `docs/en/reference/manifest.md` regenerated clean and told
    plugin authors the reserved platform key is spelled `NOARCH_PLATFORM_KEY`.
    Nothing was empty and no check was red — the page simply said something
    untrue about the interface it exists to describe.

    So an identifier that cannot be resolved raises. A fallback that prints the
    identifier is precisely the behaviour being removed, and a fallback that
    drops the element would put this back in the "quietly omits" class the
    module docstring rules out.
    """
    if part.startswith('"'):
        return part.strip('"')
    if "::" in part:
        return part.strip('"').rpartition("::")[2]
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
        value = const_str(text, part)
        if value is None:
            raise DocgenError(
                f"`{const_name}` names `{part}`, which is neither a string literal nor a "
                f"`const {part}: &str = \"…\";` in the same file. docgen cannot say which "
                f"value it stands for, and printing the identifier would put a Rust name "
                f"on the page where the value an author has to type belongs."
            )
        return value
    return part.strip('"')


def const_list(text: str, name: str) -> list[str] | None:
    """`pub const NAME: &[...] = &[ ... ];` as a list of the values it holds."""
    match = re.search(rf"const\s+{name}\s*:\s*[^=]+=\s*&\[", text)
    if not match:
        return None
    end = text.index("];", match.end())
    body = text[match.end() : end]
    body = re.sub(r"//[^\n]*", "", body)
    out = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(_const_element(text, name, part))
    return out


def const_doc(text: str, name: str) -> str:
    """The doc comment above a `const`."""
    match = re.search(rf"^(pub )?const\s+{name}\b", text, re.MULTILINE)
    if not match:
        return ""
    doc_lines: list[str] = []
    for line in reversed(text[: match.start()].rstrip().split("\n")):
        stripped = line.strip()
        if stripped.startswith("///"):
            doc_lines.insert(0, stripped)
        else:
            break
    return _dedent_doc(doc_lines)


def fn_literal(text: str, name: str) -> str | None:
    """The literal a one-expression `fn name() -> T` returns.

    `fn default_cwd() -> String { ".".to_string() }` is `.`. Used for serde's
    `#[serde(default = "fn")]`, where the default value is a fact the manifest
    reference has to state and only the function body carries.
    """
    match = re.search(rf"fn\s+{name}\s*\([^)]*\)\s*->\s*[^{{]+\{{(.*?)\}}", text, re.DOTALL)
    if not match:
        return None
    body = match.group(1).strip()
    body = re.sub(r"\.to_string\(\)$|\.into\(\)$|\.to_owned\(\)$", "", body).strip()
    return body.strip('"') or None


def match_arms(text: str, fn_name: str) -> dict[str, str]:
    """`Enum::Variant => "value",` arms of a named function, in order."""
    match = re.search(rf"fn\s+{fn_name}\s*\(", text)
    if not match:
        return {}
    body = _block(text, match.end())
    return {
        variant: value
        for variant, value in re.findall(r"(?:\w+::)?(\w+)\s*=>\s*\"([^\"]*)\"", body)
    }
