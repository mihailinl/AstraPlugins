"""Loader and validator for `spec/hooks.yaml`.

Dependency-free on purpose. `spec/hooks.yaml` is written in the same tiny YAML
subset `spec/limits.yaml` uses, so a CI runner without PyYAML can still gate the
build. When PyYAML *is* importable we parse the file both ways and assert the
two results agree — that is what keeps the file honest YAML rather than a
lookalike only this parser understands.

Subset supported:
  * `# ...` comment lines, blank lines
  * top-level `key: scalar`
  * `hooks:` followed by a block sequence of FLAT mappings:
        hooks:
          - key: scalar
            key: scalar
Scalars are `"quoted"`, `'quoted'`, an integer, `true`/`false`, or a bare
string. A bare string may not contain `#` (quote it instead), which is the one
place this parser is stricter than YAML — and the reason the PyYAML
cross-check below can be an equality assertion.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "spec" / "hooks.yaml"

LANGUAGES = ("rust", "python", "typescript")
LANGUAGE_LABELS = {"rust": "Rust", "python": "Python", "typescript": "TypeScript"}
SERVICES = ("PluginCapabilityService", "PluginHostService")
DIRECTIONS = {"PluginCapabilityService": "daemon->plugin", "PluginHostService": "plugin->daemon"}
REQUIREMENTS = ("required", "optional")
ROUTINGS = ("live", "unrouted", "deprecated")
STREAMINGS = ("unary", "server", "client", "bidi")
STATUSES = ("stable", "planned", "n/a")

REQUIRED_FIELDS = (
    "rpc", "service", "direction", "capability", "requirement",
    "routing", "since", "streaming", "daemon_calls", "summary",
) + LANGUAGES

OPTIONAL_FIELDS = ("note",) + tuple(
    f"{lang}_{suffix}" for lang in LANGUAGES for suffix in ("issue", "grace_until", "reason")
)


class SpecError(Exception):
    """The spec file is malformed. Always carries the line number."""


# ── the tiny parser ──────────────────────────────────────────────────────────

def _scalar(raw: str, lineno: int):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        body = raw[1:-1]
        if raw[0] in body:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: nested {raw[0]} in a quoted scalar")
        return body
    if "#" in raw:
        raise SpecError(
            f"{SPEC_PATH.name}:{lineno}: '#' in a bare scalar is ambiguous — quote the value"
        )
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse(text: str) -> dict:
    """Parse the subset. Returns {top-level keys..., 'hooks': [ {..}, .. ]}."""
    out: dict = {}
    hooks: list[dict] = []
    in_hooks = False
    current: dict | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            if stripped == "hooks:":
                in_hooks = True
                current = None
                continue
            in_hooks = False
            current = None
            if ":" not in stripped:
                raise SpecError(f"{SPEC_PATH.name}:{lineno}: expected `key: value`")
            key, _, value = stripped.partition(":")
            out[key.strip()] = _scalar(value, lineno)
            continue

        if not in_hooks:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: indented line outside `hooks:`")

        if stripped.startswith("- "):
            if indent != 2:
                raise SpecError(f"{SPEC_PATH.name}:{lineno}: sequence item must be indented 2")
            current = {}
            hooks.append(current)
            stripped = stripped[2:].strip()
        elif indent != 4:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: hook field must be indented 4")

        if current is None:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: field before the first `- `")
        if ":" not in stripped:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: expected `key: value`")
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key in current:
            raise SpecError(f"{SPEC_PATH.name}:{lineno}: duplicate field `{key}`")
        current[key] = _scalar(value, lineno)
        current.setdefault("_lines", {})
        current["_lines"][key] = lineno

    out["hooks"] = hooks
    return out


def _cross_check_against_pyyaml(text: str, parsed: dict) -> None:
    """If PyYAML is here, our parse must equal its parse. Keeps the file real YAML."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return
    reference = yaml.safe_load(text)
    ours = {k: v for k, v in parsed.items() if k != "hooks"}
    theirs = {k: v for k, v in reference.items() if k != "hooks"}
    if ours != theirs:
        raise SpecError(f"tools/parity/spec.py disagrees with PyYAML on the top level: {ours} vs {theirs}")
    for mine, yours in zip(parsed["hooks"], reference["hooks"]):
        mine = {k: v for k, v in mine.items() if k != "_lines"}
        yours = {
            k: (v.isoformat() if isinstance(v, datetime.date) else v)
            for k, v in yours.items()
        }
        if mine != yours:
            raise SpecError(
                f"tools/parity/spec.py disagrees with PyYAML on hook "
                f"{mine.get('rpc')}: {mine} vs {yours}"
            )


# ── validation ───────────────────────────────────────────────────────────────

def _validate(doc: dict) -> None:
    for key in ("protocol", "proto", "astra_daemon_root", "capabilities"):
        if key not in doc:
            raise SpecError(f"{SPEC_PATH.name}: missing top-level `{key}`")
    vocabulary = set(str(doc["capabilities"]).split())
    seen: set[str] = set()

    for hook in doc["hooks"]:
        lines = hook.get("_lines", {})
        rpc = hook.get("rpc")
        where = f"{SPEC_PATH.name}:{lines.get('rpc', '?')}"
        if not rpc:
            raise SpecError(f"{where}: hook has no `rpc`")
        if rpc in seen:
            raise SpecError(f"{where}: duplicate row for `{rpc}`")
        seen.add(rpc)

        for field in REQUIRED_FIELDS:
            if field not in hook:
                raise SpecError(f"{where}: `{rpc}` is missing `{field}`")
        for field in hook:
            if field != "_lines" and field not in REQUIRED_FIELDS and field not in OPTIONAL_FIELDS:
                raise SpecError(f"{where}: `{rpc}` has unknown field `{field}`")

        if hook["service"] not in SERVICES:
            raise SpecError(f"{where}: `{rpc}` service must be one of {SERVICES}")
        if hook["direction"] != DIRECTIONS[hook["service"]]:
            raise SpecError(
                f"{where}: `{rpc}` on {hook['service']} must be "
                f"`{DIRECTIONS[hook['service']]}`, not `{hook['direction']}`"
            )
        if hook["capability"] not in vocabulary:
            raise SpecError(
                f"{where}: `{rpc}` capability `{hook['capability']}` is not in the "
                f"vocabulary — the daemon would never enable it"
            )
        for field, allowed in (
            ("requirement", REQUIREMENTS), ("routing", ROUTINGS), ("streaming", STREAMINGS)
        ):
            if hook[field] not in allowed:
                raise SpecError(f"{where}: `{rpc}` {field} must be one of {allowed}")
        if not isinstance(hook["since"], int):
            raise SpecError(f"{where}: `{rpc}` since must be an integer protocol version")
        if hook["since"] > doc["protocol"]:
            raise SpecError(f"{where}: `{rpc}` since={hook['since']} is past protocol {doc['protocol']}")

        routed = hook["routing"] == "live"
        provenance = hook["daemon_calls"]
        if routed and (provenance == "none" or not re.fullmatch(r"[\w./-]+:\d+", str(provenance))):
            raise SpecError(
                f"{where}: `{rpc}` is routing=live, so `daemon_calls` must be a `file:line` "
                f"under {doc['astra_daemon_root']}, not `{provenance}`"
            )
        if not routed and provenance != "none":
            raise SpecError(
                f"{where}: `{rpc}` is routing={hook['routing']} — say `daemon_calls: none` "
                f"rather than pointing at a call site that is not one"
            )

        for lang in LANGUAGES:
            status = hook[lang]
            if status not in STATUSES:
                raise SpecError(f"{where}: `{rpc}` {lang} status must be one of {STATUSES}")
            if status == "planned":
                for suffix in ("issue", "grace_until"):
                    if not hook.get(f"{lang}_{suffix}"):
                        raise SpecError(
                            f"{where}: `{rpc}` {lang}=planned needs `{lang}_{suffix}` — a "
                            f"promise with no deadline is not a promise"
                        )
                try:
                    datetime.date.fromisoformat(str(hook[f"{lang}_grace_until"]))
                except ValueError as exc:
                    raise SpecError(
                        f"{where}: `{rpc}` {lang}_grace_until is not an ISO date: {exc}"
                    ) from exc
            elif status == "n/a" and not hook.get(f"{lang}_reason"):
                raise SpecError(f"{where}: `{rpc}` {lang}=n/a needs `{lang}_reason`")
            for suffix in ("issue", "grace_until"):
                if status != "planned" and hook.get(f"{lang}_{suffix}"):
                    raise SpecError(f"{where}: `{rpc}` {lang}={status} must not carry `{lang}_{suffix}`")
            if status != "n/a" and hook.get(f"{lang}_reason"):
                raise SpecError(f"{where}: `{rpc}` {lang}={status} must not carry `{lang}_reason`")


def load(path: Path = SPEC_PATH) -> dict:
    """Parse, cross-check, validate. Raises `SpecError` with a line number."""
    text = path.read_text(encoding="utf-8")
    doc = parse(text)
    _cross_check_against_pyyaml(text, doc)
    _validate(doc)
    return doc


def grace_until(hook: dict, lang: str) -> datetime.date | None:
    raw = hook.get(f"{lang}_grace_until")
    return datetime.date.fromisoformat(str(raw)) if raw else None
