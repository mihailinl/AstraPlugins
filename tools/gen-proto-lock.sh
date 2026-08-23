#!/usr/bin/env bash
#
# gen-proto-lock.sh — compare proto/plugin.proto against the daemon's astra.proto
#                     and write proto/ASTRA_PROTO.lock from what it found.
#
#   tools/gen-proto-lock.sh --astra-dir ../Astra/astra-rs            # write
#   tools/gen-proto-lock.sh --astra-dir _astra/astra-rs --check      # verify only
#
# ── what the lock is for ───────────────────────────────────────────────────
#
# Astra is private. Every pull request from a fork runs CI without
# ASTRA_REPO_TOKEN, so it cannot see the daemon's astra.proto at all. Those runs
# check proto/ASTRA_PROTO.lock instead: three values recorded the last time the
# two repositories were really compared. Verifying them proves the protocol has
# not moved since that comparison — nothing more, and the workflow says so.
#
# That guarantee is worth exactly as much as the provenance of the lock. Its
# value is that the hashes were produced by a process that regenerated the slice
# from astra.proto and found it identical, not by somebody typing numbers until
# degraded mode went green. So:
#
#   THE LOCK IS STILL NOT HAND-WRITTEN. This script is its only author.
#
# It used to be a heredoc inside .github/workflows/ci.yml, which made CI holding
# a token the only thing on earth that could refresh it — so a protocol change
# left the branch unmergeable until a maintainer re-ran the job, and a
# maintainer sitting on both checkouts had no supported way to do the work. The
# generator moved here; ci.yml calls it with `--check`. One definition of the
# file format, two callers, and the check and the write cannot drift apart
# because they are the same code path.
#
# ── what it verifies before it writes a byte ───────────────────────────────
#
#   1. the Astra checkout carries the slicer, its surface list and astra.proto;
#   2. `proto-slice --stdout` regenerates the plugin-facing slice from THAT
#      astra.proto and it is byte-identical to proto/plugin.proto — this is the
#      check that makes the lock mean something. Hashing the two files without
#      it would happily pin a hand-edited plugin.proto;
#   3. plugin.proto's `// source-sha256:` header is the real hash of the
#      astra.proto it was cut from, so a doctored header cannot launder a
#      protocol change through the lock.
#
# Only then are the three values written. `--check` runs all of it and diffs the
# result against the committed file instead of writing.
#
# Requires: cargo (builds the slicer), sha256sum or shasum.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_REL="proto/ASTRA_PROTO.lock"
PROTO_REL="proto/plugin.proto"

astra_dir=""
check_only=0

usage() {
    cat <<'USAGE'
usage: tools/gen-proto-lock.sh --astra-dir <path-to-astra-rs> [--check]

  --astra-dir <path>  an Astra checkout's astra-rs/ directory. It must carry
                      tools/proto-slice, astra-proto/plugin-surface.toml and
                      astra-proto/src/astra.proto.
  --check             do not write; fail if proto/ASTRA_PROTO.lock differs from
                      what this run would have written.

Also read from the environment as ASTRA_RS_DIR, which is what tools/gen-limits.mjs
and tools/check-manifest-crate.sh already use.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --astra-dir) astra_dir="${2:-}"; shift 2 ;;
        --check) check_only=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'gen-proto-lock: unknown argument %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$astra_dir" ]; then
    astra_dir="${ASTRA_RS_DIR:-}"
fi
if [ -z "$astra_dir" ]; then
    printf 'gen-proto-lock: --astra-dir is required.\n\n' >&2
    usage >&2
    exit 2
fi
if [ ! -d "$astra_dir" ]; then
    printf 'gen-proto-lock: %s is not a directory.\n' "$astra_dir" >&2
    exit 2
fi
astra_dir="$(cd -- "$astra_dir" && pwd)"

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$1" | cut -d' ' -f1
    else
        printf 'gen-proto-lock: need sha256sum or shasum on PATH\n' >&2
        exit 2
    fi
}

# The same, over stdin — for hashing part of a file rather than a file.
sha256_stdin() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 | cut -d' ' -f1
    else
        printf 'gen-proto-lock: need sha256sum or shasum on PATH\n' >&2
        exit 2
    fi
}

# ---- 1. the checkout carries the slicer, the surface list and the source
SLICER="$astra_dir/tools/proto-slice/Cargo.toml"
SURFACE="$astra_dir/astra-proto/plugin-surface.toml"
ASTRA_PROTO="$astra_dir/astra-proto/src/astra.proto"

for p in "$SLICER" "$SURFACE" "$ASTRA_PROTO"; do
    if [ ! -f "$p" ]; then
        cat >&2 <<MSG
gen-proto-lock: FAIL $p does not exist.

$PROTO_REL is CUT from Astra's astra-proto/src/astra.proto by
astra-rs/tools/proto-slice, using astra-proto/plugin-surface.toml as the list of
what crosses the plugin boundary. This script regenerates that slice and diffs
it, so all three files must exist in the checkout it is pointed at.

Looked in: $astra_dir
If the slicer is not on that branch yet, check out the branch carrying it
(today: feat/plugin-production).
MSG
        exit 1
    fi
done
printf 'gen-proto-lock: ok   %s carries the slicer and its surface file\n' "$astra_dir"

# ---- 2. the slice regenerates byte-identically
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Build into a scratch directory rather than the Astra checkout's target/: this
# script reads that tree and must not leave anything behind in it.
CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$tmp/target}" \
    cargo run --quiet --manifest-path "$SLICER" -- --stdout > "$tmp/upstream-plugin.proto"

if ! cmp -s "$tmp/upstream-plugin.proto" "$REPO_ROOT/$PROTO_REL"; then
    printf 'gen-proto-lock: FAIL %s is not what the daemon'\''s proto slices to.\n' "$PROTO_REL" >&2
    diff -u "$REPO_ROOT/$PROTO_REL" "$tmp/upstream-plugin.proto" | head -60 >&2 || true
    cat >&2 <<'MSG'

Fix in the Astra repo, never here:
    cargo run --manifest-path astra-rs/tools/proto-slice/Cargo.toml
then copy astra-proto/generated/plugin.proto to AstraPlugins/proto/plugin.proto
and run tools/sync-proto.sh.
MSG
    exit 1
fi
printf 'gen-proto-lock: ok   %s is byte-identical to the regenerated slice\n' "$PROTO_REL"

# ---- 3. the header's own digests
#
# TWO digests, and the difference between them is the whole point.
#
#   surface-sha256  the plugin-facing BODY below the header. Moves only when
#                   something a plugin can see moves. This is the one this
#                   repository cares about, and the one it can verify from its
#                   own bytes: no Astra checkout, no slicer, no network.
#
#   source-sha256   which astra.proto produced these bytes. Moves on EVERY edit
#                   to that file, including one that changes nothing here. It is
#                   Astra's provenance claim, checked in Astra by a canary that
#                   lives beside the source.
#
# Until 2026-08-23 there was only the second, and this script keyed on it. That
# made a comment appended to astra.proto turn this repository red and cost a
# seven-file commit — the slice, two vendored copies, PROTO_VERSION, this lock,
# a generated TS file and a docs page — for a change no plugin could observe. A
# chore with no payoff is exactly how the generated slice stopped being
# generated in the first place, so it was worth removing rather than enduring.
#
# `source-sha256` is therefore OPTIONAL here and is on its way out of the file
# altogether. While it is present it is still checked; when it goes, this says
# so out loud rather than silently checking nothing.
protocol="$(sed -n 's|^// protocol: *||p' "$REPO_ROOT/$PROTO_REL" | head -n1)"
astra_sha="$(sed -n 's|^// source-sha256: *||p' "$REPO_ROOT/$PROTO_REL" | head -n1)"
surface_sha="$(sed -n 's|^// surface-sha256: *||p' "$REPO_ROOT/$PROTO_REL" | head -n1)"
plugin_sha="$(sha256_of "$REPO_ROOT/$PROTO_REL")"
real_astra_sha="$(sha256_of "$ASTRA_PROTO")"

# The body is everything after the leading run of `//` lines. That is the
# emitter's own definition — it hashes `emit(index, sel, "")`, the emission with
# an empty header, and asserts the real header is a prefix of the real emission
# — and it is deliberately NOT "after the second rule line": the body contains a
# rule line of its own, so counting them is right by luck.
body_digest() { awk 'f || !/^\/\//{f=1; print}' "$1" | sha256_stdin; }

if [ -z "$protocol" ]; then
    printf 'gen-proto-lock: FAIL %s carries no `// protocol: N` header line.\n' "$PROTO_REL" >&2
    exit 1
fi

if [ -z "$surface_sha" ]; then
    printf 'gen-proto-lock: FAIL %s carries no `// surface-sha256:` header line.\n' "$PROTO_REL" >&2
    printf '                      The slicer has emitted one since Astra 8413bea8. A slice without\n' >&2
    printf '                      it was cut by an older tool: regenerate rather than hand-add it.\n' >&2
    exit 1
fi
real_surface_sha="$(body_digest "$REPO_ROOT/$PROTO_REL")"
if [ "$surface_sha" != "$real_surface_sha" ]; then
    printf 'gen-proto-lock: FAIL %s'\''s surface-sha256 header says %s\n' "$PROTO_REL" "$surface_sha" >&2
    printf '                      but its own body hashes to          %s\n' "$real_surface_sha" >&2
    printf '                      Something edited the body of this file by hand. The header cannot\n' >&2
    printf '                      have been written by the slicer for these bytes.\n' >&2
    exit 1
fi
printf 'gen-proto-lock: ok   surface-sha256 header is the real hash of this file'\''s own body\n'

if [ -n "$astra_sha" ]; then
    if [ "$astra_sha" != "$real_astra_sha" ]; then
        printf 'gen-proto-lock: FAIL %s'\''s source-sha256 header says %s\n' "$PROTO_REL" "$astra_sha" >&2
        printf '                      but astra.proto hashes to           %s\n' "$real_astra_sha" >&2
        exit 1
    fi
    printf 'gen-proto-lock: ok   source-sha256 header is the real hash of astra.proto\n'
else
    printf 'gen-proto-lock: note source-sha256 NOT CHECKED — this slice carries no such header.\n'
    printf '                      Provenance now lives beside the source in the Astra repo, which is\n'
    printf '                      where it is guaranteed. surface-sha256 above is what this file\n'
    printf '                      asserts about itself, and it was checked.\n'
fi

# ---- 4. the file
cat > "$tmp/ASTRA_PROTO.lock" <<EOF
# The upstream protocol, pinned by a process that could see it.
#
# GENERATED by tools/gen-proto-lock.sh — DO NOT EDIT.
#
# Written only after that script regenerated the slice from Astra's astra.proto
# and found it byte-identical to proto/plugin.proto, which means it can only be
# written by someone holding a checkout of the private Astra repository: CI's
# proto-upstream job in full mode, or a maintainer running the script directly.
# Runs WITHOUT that access (every fork PR) verify these three values instead,
# and say plainly that they did not contact upstream.
#
#   protocol             the \`// protocol: N\` header of proto/plugin.proto
#   plugin_proto_sha256  sha256 of proto/plugin.proto, header included
#   surface_sha256       sha256 of its plugin-facing BODY, header excluded — the
#                        value a run with no upstream access can recompute from
#                        the file in front of it, and the one that moves only
#                        when something a plugin can see moves
#   astra_proto_sha256   sha256 of the astra.proto it was cut from. OPTIONAL and
#                        being retired: it moves on every edit to that file,
#                        including edits with no effect here, and its guarantee
#                        is kept in the Astra repository beside the source. The
#                        line is absent once the slicer stops emitting the
#                        header, and its absence is reported, not assumed.
#
protocol=$protocol
plugin_proto_sha256=$plugin_sha
surface_sha256=$surface_sha
EOF
if [ -n "$astra_sha" ]; then
    printf 'astra_proto_sha256=%s\n' "$astra_sha" >> "$tmp/ASTRA_PROTO.lock"
fi

if [ "$check_only" = 1 ]; then
    if ! cmp -s "$tmp/ASTRA_PROTO.lock" "$REPO_ROOT/$LOCK_REL"; then
        printf 'gen-proto-lock: FAIL %s is stale. Commit this:\n\n' "$LOCK_REL" >&2
        cat "$tmp/ASTRA_PROTO.lock" >&2
        printf '\nRegenerate with: tools/gen-proto-lock.sh --astra-dir %s\n' "$astra_dir" >&2
        exit 1
    fi
    printf 'gen-proto-lock: ok   %s is current\n' "$LOCK_REL"
    exit 0
fi

if cmp -s "$tmp/ASTRA_PROTO.lock" "$REPO_ROOT/$LOCK_REL"; then
    printf 'gen-proto-lock: ok   %s was already current\n' "$LOCK_REL"
else
    cp -f "$tmp/ASTRA_PROTO.lock" "$REPO_ROOT/$LOCK_REL"
    printf 'gen-proto-lock: wrote %s\n' "$LOCK_REL"
fi
# The summary names surface before plugin, because surface is the number a
# reader can act on. `astra=` appears only when there IS one — an ellipsis after
# an empty value reads as a truncated hash rather than as an absence, which is
# the same trick as a check that skips quietly, in one line of output.
if [ -n "$astra_sha" ]; then
    printf '                protocol=%s surface=%s… plugin=%s… astra=%s…\n' \
        "$protocol" "${surface_sha:0:12}" "${plugin_sha:0:12}" "${astra_sha:0:12}"
else
    printf '                protocol=%s surface=%s… plugin=%s… (no source-sha256 in this slice)\n' \
        "$protocol" "${surface_sha:0:12}" "${plugin_sha:0:12}"
fi
