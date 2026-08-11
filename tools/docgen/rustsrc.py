"""A very small reader for the Rust sources docgen derives pages from.

Not a Rust parser. It knows four shapes, and every one of them is a shape the
files it is pointed at actually use:

  * `#[derive(..., Deserialize)] pub struct Name { ... }` with `#[serde(...)]`
    attributes and `///` doc comments on the fields;
  * `pub enum Name { Variant, ... }`, likewise;
  * `pub const NAME: &[&str] = &["a", "b"];` and
    `pub const NAME: &[Type] = &[Type::A, Type::B];`;
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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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


def const_list(text: str, name: str) -> list[str] | None:
    """`pub const NAME: &[...] = &[ ... ];` as a list of stripped elements."""
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
        out.append(part.strip('"').rpartition("::")[2] if "::" in part else part.strip('"'))
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
