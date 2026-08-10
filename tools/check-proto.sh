#!/usr/bin/env bash
#
# check-proto.sh — assert this repo still has exactly one protocol.
#
# Read tools/sync-proto.sh for why the two vendored copies exist. This script is
# the enforcement half: it fails, loudly and with the fix in the message, if
#
#   1. proto/plugin.proto is missing, or lost its generator banner;
#   2. proto/PROTO_VERSION disagrees with proto/plugin.proto (protocol or sha256);
#   3. any vendored copy is not byte-identical to proto/plugin.proto;
#   4. a plugin.proto exists anywhere else in the working tree — the CLI and the
#      examples used to carry 348-line fossils, and the TypeScript SDK a stale
#      2479-line one, all of which drifted silently for months.
#
# Every failure is recoverable with `tools/sync-proto.sh`, except (4), which is a
# deletion, and (1), which means regenerating the proto upstream.
#
# Usage: tools/check-proto.sh          # exit 0 if in sync, 1 otherwise
#
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

CANONICAL_REL="proto/plugin.proto"
VERSION_REL="proto/PROTO_VERSION"
SYNC="tools/sync-proto.sh"

# Must match COPIES in tools/sync-proto.sh. The unknown-copy scan below turns a
# divergence between the two lists into a hard failure rather than a blind spot.
COPIES=(
    "astra-plugin-sdk/proto/plugin.proto"
    "astra-plugin-sdk-python/astra_plugin_sdk/proto/plugin.proto"
)

failures=0

fail() {
    printf 'check-proto: FAIL %s\n' "$1" >&2
    shift
    for line in "$@"; do printf '                  %s\n' "$line" >&2; done
    failures=$((failures + 1))
}

ok() { printf 'check-proto: ok   %s\n' "$1"; }

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$1" | cut -d' ' -f1
    else
        printf 'check-proto: need sha256sum or shasum on PATH\n' >&2
        exit 2
    fi
}

canonical="$REPO_ROOT/$CANONICAL_REL"
if [ ! -f "$canonical" ]; then
    printf 'check-proto: FAIL %s does not exist. It is the source of every copy;\n' "$CANONICAL_REL" >&2
    printf '                  regenerate it in the Astra repo with astra-rs/tools/proto-slice.\n' >&2
    exit 1
fi

# ---- 1. the canonical file is the generator's output, not something hand-rolled
if grep -q 'DO NOT EDIT' "$canonical"; then
    ok "$CANONICAL_REL carries its DO NOT EDIT banner"
else
    fail "$CANONICAL_REL has lost its \`GENERATED FILE — DO NOT EDIT\` banner." \
        "It is produced by astra-rs/tools/proto-slice; hand edits belong in" \
        "astra-proto/src/astra.proto or plugin-surface.toml, never here."
fi

protocol="$(sed -n 's|^// protocol: *\([0-9][0-9]*\) *$|\1|p' "$canonical" | head -n1)"
if [ -z "$protocol" ]; then
    fail "$CANONICAL_REL carries no \`// protocol: N\` header line." \
        "The slicer stamps it; a proto without one cannot be pinned."
fi

sha="$(sha256_of "$canonical")"

# ---- 2. PROTO_VERSION pins that protocol integer and that hash
version_file="$REPO_ROOT/$VERSION_REL"
if [ ! -f "$version_file" ]; then
    fail "$VERSION_REL does not exist. Run \`$SYNC\` to write it."
else
    pinned_protocol="$(sed -n 's|^protocol=\(.*\)$|\1|p' "$version_file" | head -n1)"
    pinned_sha="$(sed -n 's|^sha256=\(.*\)$|\1|p' "$version_file" | head -n1)"

    if [ -n "$protocol" ] && [ "$pinned_protocol" != "$protocol" ]; then
        fail "$VERSION_REL pins protocol=${pinned_protocol:-<missing>}, but $CANONICAL_REL says protocol: $protocol." \
            "Run \`$SYNC\`."
    fi
    if [ "$pinned_sha" != "$sha" ]; then
        fail "$VERSION_REL pins a stale sha256." \
            "pinned:    ${pinned_sha:-<missing>}" \
            "$CANONICAL_REL: $sha" \
            "Run \`$SYNC\`."
    fi
    if [ -n "$protocol" ] && [ "$pinned_protocol" = "$protocol" ] && [ "$pinned_sha" = "$sha" ]; then
        ok "$VERSION_REL pins protocol=$protocol sha256=${sha:0:12}…"
    fi
fi

# ---- 3. every vendored copy is byte-identical to the canonical file
for rel in "${COPIES[@]}"; do
    copy="$REPO_ROOT/$rel"
    if [ ! -f "$copy" ]; then
        fail "$rel is missing." \
            "The Rust and Python packages cannot reach outside their own root," \
            "so they vendor this copy. Run \`$SYNC\`."
        continue
    fi
    if cmp -s -- "$canonical" "$copy"; then
        ok "$rel is byte-identical to $CANONICAL_REL"
    else
        fail "$rel has drifted from $CANONICAL_REL." \
            "$CANONICAL_REL: $sha" \
            "$rel: $(sha256_of "$copy")" \
            "This copy is generated. Edit astra.proto upstream, then run \`$SYNC\`." \
            "(diff: cmp -l '$CANONICAL_REL' '$rel' | head)"
    fi
done

# ---- 4. no other plugin.proto anywhere. One protocol, four consumers, two copies.
#
# Build outputs and dependency trees are not source, so they are excluded; the
# generated TypeScript descriptor lives in src/generated/ and is JSON, not .proto.
# `build/` and `*.egg-info/` are on the list because `python -m build` copies the
# vendored proto into astra-plugin-sdk-python/build/lib/ — running the wheel
# build and then this script would otherwise report the packaging copy that
# proves the packaging works as a stray copy that must be deleted.
expected_set="$(printf '%s\n' "$CANONICAL_REL" "${COPIES[@]}" | LC_ALL=C sort)"
found_set="$(
    cd -- "$REPO_ROOT" && find . -name 'plugin.proto' \
        -not -path './.git/*' \
        -not -path '*/target/*' \
        -not -path '*/node_modules/*' \
        -not -path '*/.venv/*' \
        -not -path '*/dist/*' \
        -not -path '*/build/*' \
        -not -path '*.egg-info/*' \
        -print | sed 's|^\./||' | LC_ALL=C sort
)"

unexpected="$(LC_ALL=C comm -13 <(printf '%s\n' "$expected_set") <(printf '%s\n' "$found_set") || true)"
if [ -n "$unexpected" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        fail "$rel is an unexpected copy of the protocol." \
            "Only $CANONICAL_REL and the ${#COPIES[@]} packaging copies may exist." \
            "The CLI ships no proto (scaffolds get theirs from the SDK dependency) and" \
            "the TypeScript SDK generates src/generated/descriptor.json from the canonical" \
            "file at build time. Delete this file."
    done <<EOF
$unexpected
EOF
else
    ok "no stray copies of plugin.proto in the working tree"
fi

if [ "$failures" -ne 0 ]; then
    printf '\ncheck-proto: %d check(s) failed. Most of them are fixed by:\n\n    %s\n\n' \
        "$failures" "$SYNC" >&2
    exit 1
fi

printf 'check-proto: one protocol, protocol=%s, %d vendored cop%s in sync.\n' \
    "$protocol" "${#COPIES[@]}" "$([ "${#COPIES[@]}" -eq 1 ] && echo y || echo ies)"
