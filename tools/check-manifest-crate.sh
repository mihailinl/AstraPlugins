#!/usr/bin/env bash
#
# check-manifest-crate.sh — assert `plugin.toml` still has exactly one definition.
#
# The daemon, `astra-plugin` and (from plan task 3.3) the registry bot all parse
# a plugin manifest. They used to do it with three different structs, and the
# CLI's fork grew a `ui_panels` capability the daemon has never had. Serde drops
# unknown fields, so the disagreement produced no error anywhere: three shipped
# examples declared `ui_panels`, the daemon read no capabilities from them, and
# the only symptom was `astra-plugin check` printing "No capabilities enabled".
#
# The fix is one crate, `astra-plugin-manifest`, VENDORED rather than published —
# the reasoning is in the crate's README and is a decision, not an accident. This
# script is the half that makes vendoring safe: it fails when the copy in this
# repo has drifted from the source of truth in Astra.
#
# WHAT IS COMPARED, and why exactly this:
#
#   * `src/**` and `README.md`, BYTE-FOR-BYTE. That is where behaviour lives, so
#     that is where drift is forbidden outright.
#   * `Cargo.toml`, on its dependency NAMES only. The two files legitimately
#     differ — upstream inherits versions from Astra's workspace and carries an
#     optional `astra-core` for the `astra-host` feature; this copy spells
#     versions out and leaves that feature empty, because `astra-plugin`
#     validates a manifest and is not an Astra. Comparing names still catches
#     the failure that matters: a dependency added upstream and forgotten here.
#
# Usage:
#   tools/check-manifest-crate.sh            # exit 0 if in sync, 1 otherwise
#   tools/check-manifest-crate.sh --sync     # copy upstream over the vendored copy
#
# The upstream checkout is found next to this repository by default. Override
# with ASTRA_REPO=/path/to/Astra when it lives somewhere else; when it is absent
# entirely (a CI job that clones only this repo, a contributor without the Astra
# source) the script SKIPS rather than fails, and says so — a check nobody can
# run locally gets ignored, and an equivalence test is worth nothing if it is
# ignored.
#
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Relative to each side's crate root. Everything here is compared byte-for-byte.
IDENTICAL=(
    "src/lib.rs"
    "src/manifest.rs"
    "src/capabilities.rs"
    "src/platform.rs"
    "README.md"
)

# A dependency present upstream and deliberately absent here. See the header.
UPSTREAM_ONLY_DEPS=("astra-core")

VENDORED="$REPO_ROOT/astra-plugin-cli/vendor/astra-plugin-manifest"

# Where Astra is checked out. Sibling of this repository unless told otherwise.
ASTRA_REPO="${ASTRA_REPO:-$(cd -- "$REPO_ROOT/.." && pwd)/Astra}"
UPSTREAM="$ASTRA_REPO/astra-rs/astra-plugin-manifest"

SYNC_CMD="tools/check-manifest-crate.sh --sync"

mode="check"
if [ "${1:-}" = "--sync" ]; then
    mode="sync"
elif [ "$#" -gt 0 ]; then
    printf 'check-manifest-crate: unknown argument %s (expected --sync or nothing)\n' "$1" >&2
    exit 2
fi

failures=0

fail() {
    printf 'check-manifest-crate: FAIL %s\n' "$1" >&2
    shift
    for line in "$@"; do printf '                           %s\n' "$line" >&2; done
    failures=$((failures + 1))
}

ok() { printf 'check-manifest-crate: ok   %s\n' "$1"; }

# ---- 0. both sides exist ----------------------------------------------------
if [ ! -d "$VENDORED" ]; then
    printf 'check-manifest-crate: FAIL %s does not exist.\n' "${VENDORED#"$REPO_ROOT"/}" >&2
    printf '                           astra-plugin-cli depends on it by path. Run `%s`.\n' "$SYNC_CMD" >&2
    exit 1
fi

if [ ! -d "$UPSTREAM" ]; then
    printf 'check-manifest-crate: SKIP the Astra checkout is not at %s.\n' "$ASTRA_REPO"
    printf '                           `plugin.toml` is defined in Astra and vendored here; without\n'
    printf '                           that checkout there is nothing to compare against. Set\n'
    printf '                           ASTRA_REPO=/path/to/Astra to run this check.\n'
    exit 0
fi

# ---- 1. sync mode: copy, then fall through and verify -----------------------
if [ "$mode" = "sync" ]; then
    printf 'check-manifest-crate: syncing %s -> %s\n' "$UPSTREAM" "$VENDORED"
    for rel in "${IDENTICAL[@]}"; do
        src="$UPSTREAM/$rel"
        if [ ! -f "$src" ]; then
            printf 'check-manifest-crate: FAIL upstream has no %s — nothing to copy.\n' "$rel" >&2
            exit 1
        fi
        mkdir -p -- "$(dirname -- "$VENDORED/$rel")"
        cp -- "$src" "$VENDORED/$rel"
        printf '                           copied %s\n' "$rel"
    done
    printf 'check-manifest-crate: Cargo.toml is NOT copied — it is the one intentional\n'
    printf '                           difference. If upstream gained a dependency, add it to\n'
    printf '                           %s by hand.\n' "${VENDORED#"$REPO_ROOT"/}/Cargo.toml"
fi

# ---- 2. every shared file is byte-identical ---------------------------------
for rel in "${IDENTICAL[@]}"; do
    up="$UPSTREAM/$rel"
    ven="$VENDORED/$rel"
    if [ ! -f "$up" ]; then
        fail "upstream is missing $rel." \
            "The source of truth is $UPSTREAM." \
            "A file deleted upstream must be deleted here and dropped from IDENTICAL in this script."
        continue
    fi
    if [ ! -f "$ven" ]; then
        fail "the vendored copy is missing $rel." "Run \`$SYNC_CMD\`."
        continue
    fi
    if cmp -s -- "$up" "$ven"; then
        ok "$rel is byte-identical to Astra's"
    else
        fail "$rel has drifted from Astra's copy." \
            "The daemon and the CLI would parse the same plugin.toml differently — that is" \
            "the defect this crate exists to prevent, not a formatting nit." \
            "diff: diff -u '$up' '$ven'" \
            "fix:  $SYNC_CMD   (upstream wins; edit Astra's copy, never this one)"
    fi
done

# ---- 3. no file exists on one side and not the other ------------------------
#
# A new module upstream that nobody added to IDENTICAL would otherwise be an
# invisible hole: the check above only looks at files it was told about.
list_src() {
    (cd -- "$1" && find src -type f -name '*.rs' -print | LC_ALL=C sort)
}
declared="$(printf '%s\n' "${IDENTICAL[@]}" | grep '^src/' | LC_ALL=C sort)"
for side in "$UPSTREAM" "$VENDORED"; do
    actual="$(list_src "$side")"
    extra="$(LC_ALL=C comm -13 <(printf '%s\n' "$declared") <(printf '%s\n' "$actual") || true)"
    if [ -n "$extra" ]; then
        while IFS= read -r rel; do
            [ -n "$rel" ] || continue
            fail "$side/$rel is a source file this script does not compare." \
                "Add it to IDENTICAL in tools/check-manifest-crate.sh, then \`$SYNC_CMD\`."
        done <<EOF
$extra
EOF
    fi
done

# ---- 4. the dependency sets agree -------------------------------------------
#
# Names only. Version requirements differ by construction (upstream inherits
# them from Astra's workspace), and that difference is inspected by a human when
# a dependency is added, not by this script.
dep_names() {
    awk '
        /^\[/ { in_deps = ($0 == "[dependencies]") ; next }
        !in_deps { next }
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        {
            line = $0
            sub(/[[:space:]]*=.*$/, "", line)
            sub(/\..*$/, "", line)            # `serde.workspace = true`
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
            if (line != "") print line
        }
    ' "$1" | LC_ALL=C sort -u
}

up_deps="$(dep_names "$UPSTREAM/Cargo.toml")"
ven_deps="$(dep_names "$VENDORED/Cargo.toml")"
for d in "${UPSTREAM_ONLY_DEPS[@]}"; do
    up_deps="$(printf '%s\n' "$up_deps" | grep -vx -- "$d" || true)"
done

if [ "$up_deps" = "$ven_deps" ]; then
    ok "Cargo.toml dependency names agree ($(printf '%s' "$up_deps" | tr '\n' ' '))"
else
    missing="$(LC_ALL=C comm -23 <(printf '%s\n' "$up_deps") <(printf '%s\n' "$ven_deps") || true)"
    surplus="$(LC_ALL=C comm -13 <(printf '%s\n' "$up_deps") <(printf '%s\n' "$ven_deps") || true)"
    detail=()
    [ -n "$missing" ] && detail+=("upstream has, vendored lacks: $(printf '%s' "$missing" | tr '\n' ' ')")
    [ -n "$surplus" ] && detail+=("vendored has, upstream lacks: $(printf '%s' "$surplus" | tr '\n' ' ')")
    fail "the two Cargo.toml files declare different dependencies." \
        "${detail[@]}" \
        "Versions may differ (upstream inherits Astra's workspace); the SET may not." \
        "Edit ${VENDORED#"$REPO_ROOT"/}/Cargo.toml by hand — \`--sync\` does not touch it."
fi

if [ "$failures" -ne 0 ]; then
    printf '\ncheck-manifest-crate: %d check(s) failed. Most of them are fixed by:\n\n    %s\n\n' \
        "$failures" "$SYNC_CMD" >&2
    exit 1
fi

printf 'check-manifest-crate: one plugin.toml definition, %d file(s) in sync.\n' "${#IDENTICAL[@]}"
