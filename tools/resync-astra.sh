#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
#
# resync-astra.sh — the whole upstream resync, one command.
#
#   tools/resync-astra.sh --astra-dir ../Astra
#   tools/resync-astra.sh --astra-dir ../Astra --no-commit
#   tools/resync-astra.sh --astra-dir ../Astra --skip-ui-kit --skip-docgen-check
#
# Astra main moves the plugin proto slice and the UI Kit out from under this
# repository with no warning: nothing here subscribes to Astra's commits, so
# the first sign is `proto (upstream drift)` or `proto (vendored copies)`
# turning red in a pull request that touched neither file. On 2026-11-05 that
# happened three times in one day, and each time a human re-typed the same
# eight-step recipe by hand from tools/sync-proto.sh's comments,
# gen-proto-lock.sh's comments and CONTRIBUTING.md's generated-files table.
# The docs digest swap (step 7 below) was forgotten once, which is how a proto
# resync turned the `mirror` job red too — a second CI failure with no
# connection to the first one a reader could see without already knowing this
# script's step 7 exists.
#
# This runs the whole recipe end to end and stops being able to forget a step.
# It is read-only about *whether* the protocol or the UI Kit actually moved:
# `tools/gen-proto-lock.sh` already proves that byte-for-byte, so this trusts
# it rather than re-deciding it. If nothing moved, this makes no commit — the
# steps below ran, found no diff, and said so.
#
# WHAT THIS DOES NOT DO: decide that a protocol or UI Kit change is SAFE. It
# regenerates what the generators say to regenerate and runs the checks CI
# runs. A change that is syntactically consistent but semantically wrong is a
# human's to catch in the PR this script opens.
#
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

astra_dir=""
no_commit=0
skip_ui_kit=0
skip_docgen_check=0

usage() {
    cat <<'USAGE'
usage: tools/resync-astra.sh --astra-dir <path> [OPTIONS]

  --astra-dir <path>     a checkout of the Astra repository, at the commit to
                         follow. The top of a flat checkout (since Astra
                         c703cabb6, 2026-10-23) or a checkout with astra-rs/
                         at its top (v0.2.7 or earlier) — this script tells
                         the two apart the same way CI's proto-upstream job
                         does, and resolves every path under whichever root
                         actually carries tools/proto-slice.
  --no-commit            run every generation step and stage the result, but
                         stop before the first commit this script would make.
                         Nothing after that commit point runs (the UI Kit
                         check and the final checks both need a clean,
                         committed tree at a known SHA).
  --skip-ui-kit          skip the UI Kit resync (step 8). The final checks
                         still run against whatever UI Kit state is already
                         committed.
  --skip-docgen-check    skip `tools/docgen/gen.py --check` in the final
                         checks, and with it the `cargo build --release`
                         of astra-plugin-cli that check needs. Everything
                         else in the final checks still runs.
  -h, --help             this text
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --astra-dir) astra_dir="${2:-}"; shift 2 ;;
        --no-commit) no_commit=1; shift ;;
        --skip-ui-kit) skip_ui_kit=1; shift ;;
        --skip-docgen-check) skip_docgen_check=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'resync-astra: unknown argument %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

log()  { printf 'resync-astra: %s\n' "$1"; }
die()  { printf 'resync-astra: FAIL %s\n' "$1" >&2; exit 1; }

[ -n "$astra_dir" ] || { printf 'resync-astra: --astra-dir is required.\n\n' >&2; usage >&2; exit 2; }
[ -d "$astra_dir" ] || die "$astra_dir is not a directory."
ASTRA_DIR="$(cd -- "$astra_dir" && pwd)"

# Same two shapes gen-proto-lock.sh's usage text documents, resolved the way
# ci.yml's "locate the daemon's tree in that checkout" step resolves them —
# the caller hands us a checkout, this script does not ask it which shape it
# is, it looks.
if [ -f "$ASTRA_DIR/tools/proto-slice/Cargo.toml" ]; then
    ASTRA_ROOT="$ASTRA_DIR"
elif [ -f "$ASTRA_DIR/astra-rs/tools/proto-slice/Cargo.toml" ]; then
    ASTRA_ROOT="$ASTRA_DIR/astra-rs"
else
    die "$ASTRA_DIR carries tools/proto-slice/Cargo.toml at neither its top nor astra-rs/. Not an Astra checkout with the slicer on it."
fi

# ── disk placement: dedicated build dirs, never the repos themselves ───────
: "${TMPDIR:=/tmp}"
mkdir -p "$TMPDIR"
: "${CARGO_TARGET_DIR:=$TMPDIR/resync-astra-cargo-target}"
mkdir -p "$CARGO_TARGET_DIR"
export TMPDIR CARGO_TARGET_DIR

# ---- 1. refuse a dirty tree, on both sides ---------------------------------
[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ] || die "this checkout ($REPO_ROOT) is dirty. Commit or stash before resyncing."
[ -z "$(git -C "$ASTRA_DIR" status --porcelain)" ] || die "the Astra checkout ($ASTRA_DIR) is dirty. resync-astra writes into it (step 2 regenerates the committed slice in place); it must start clean."
log "both checkouts are clean"

astra_sha="$(git -C "$ASTRA_DIR" rev-parse HEAD)"
log "following Astra@${astra_sha:0:12}… ($ASTRA_DIR, root $ASTRA_ROOT)"

# ---- 2. slice: regenerate Astra's own committed slice, in place -----------
#
# The slicer bakes CARGO_MANIFEST_DIR in at compile time (its own, not ours),
# so where WE run it from never matters to what it reads or writes — only
# --manifest-path does. What matters is CARGO_TARGET_DIR: proto-slice is its
# own workspace root (see its Cargo.toml's `[workspace]` comment), so without
# an override it would write a `target/` into the Astra checkout. Running
# with --check here would only prove Astra's astra.proto and Astra's own
# committed slice agree — a fact Astra's own CI already owns — so this runs
# it in WRITE mode and then asks git whether anything moved: that is the
# proof that the committed slice (what step 3 is about to copy) is in fact
# current. If the slicer is stale, this says so and stops; fixing it is a
# commit in Astra, not here.
log "slicing: cargo run --manifest-path tools/proto-slice/Cargo.toml (in $ASTRA_ROOT)"
(
    cd "$ASTRA_ROOT"
    CARGO_TARGET_DIR="$CARGO_TARGET_DIR/proto-slice-astra" \
        cargo run --quiet --manifest-path tools/proto-slice/Cargo.toml
)
if ! git -C "$ASTRA_ROOT" diff --quiet --exit-code -- astra-proto/generated/plugin.proto; then
    printf 'resync-astra: FAIL Astra'"'"'s committed astra-proto/generated/plugin.proto was stale —\n' >&2
    printf '                    regenerating it from astra.proto changed it. That is a bug in\n' >&2
    printf '                    Astra (its own CI should have caught this), not in this repo.\n' >&2
    printf '                    Left the regenerated bytes in place at %s for inspection:\n\n' "$ASTRA_ROOT" >&2
    git -C "$ASTRA_ROOT" diff -- astra-proto/generated/plugin.proto | head -60 >&2
    exit 1
fi
log "Astra's committed slice is current — nothing moved when regenerated"

# ---- 3. copy the canonical slice in, and fan it out to the vendored copies -
cp -- "$ASTRA_ROOT/astra-proto/generated/plugin.proto" "$REPO_ROOT/proto/plugin.proto"
bash tools/sync-proto.sh

# ---- 4. python stubs: protoc + the documented sed, with the toolchain the --
#         committed stubs themselves record -------------------------------
PY_PROTO_DIR="astra-plugin-sdk-python/astra_plugin_sdk/proto"
grpc_ver="$(sed -n "s/^GRPC_GENERATED_VERSION = '\(.*\)'\$/\1/p" "$PY_PROTO_DIR/plugin_pb2_grpc.py" | head -n1)"
[ -n "$grpc_ver" ] || die "$PY_PROTO_DIR/plugin_pb2_grpc.py has no GRPC_GENERATED_VERSION to pin to."
venv_dir="$TMPDIR/grpc-$grpc_ver"
if [ ! -x "$venv_dir/bin/python" ]; then
    log "creating venv for grpcio-tools==$grpc_ver at $venv_dir"
    uv venv --python 3.12 "$venv_dir" >/dev/null
fi
uv pip install --python "$venv_dir/bin/python" --quiet "grpcio-tools==$grpc_ver"
log "regenerating Python stubs with grpcio-tools==$grpc_ver"
(
    cd astra-plugin-sdk-python
    "$venv_dir/bin/python" -m grpc_tools.protoc \
        -I astra_plugin_sdk/proto \
        --python_out=astra_plugin_sdk/proto \
        --grpc_python_out=astra_plugin_sdk/proto \
        astra_plugin_sdk/proto/plugin.proto
    sed -i 's|^import plugin_pb2 as plugin__pb2$|from . import plugin_pb2 as plugin__pb2|' \
        astra_plugin_sdk/proto/plugin_pb2_grpc.py
)
"$venv_dir/bin/python" tools/check-python-stubs.py

# ---- 5. TypeScript descriptor ----------------------------------------------
log "regenerating the TypeScript descriptor"
(cd astra-plugin-sdk-ts && bun install --frozen-lockfile >/dev/null && bun run generate)

# ---- 6. the upstream lock ---------------------------------------------------
bash tools/gen-proto-lock.sh --astra-dir "$ASTRA_ROOT"

# ---- 7. docs: the protocol reference page, then the digest prefixes that ---
#         mirror.py pins in every translation --------------------------------
PROTOCOL_EN="docs/en/reference/protocol.md"
extract_surface() { grep -oE 'surface-sha256: [0-9a-f]{16}' "$1" | head -n1 | sed 's/^surface-sha256: //'; }
extract_plugin()  { grep -oE '(^|[^-a-z])sha256:[0-9a-f]{16}' "$1" | head -n1 | sed 's/^.*sha256://'; }

old_surface="$(extract_surface "$PROTOCOL_EN")"
old_plugin="$(extract_plugin "$PROTOCOL_EN")"
[ -n "$old_surface" ] && [ -n "$old_plugin" ] || die "$PROTOCOL_EN carries no surface-sha256/sha256 prefix to track before regenerating — docgen's protocol.py must have changed shape."

python3 tools/docgen/gen.py --only protocol

new_surface="$(extract_surface "$PROTOCOL_EN")"
new_plugin="$(extract_plugin "$PROTOCOL_EN")"
[ -n "$new_surface" ] && [ -n "$new_plugin" ] || die "$PROTOCOL_EN carries no surface-sha256/sha256 prefix after regenerating."

if [ "$old_surface" != "$new_surface" ] || [ "$old_plugin" != "$new_plugin" ]; then
    log "digest moved: surface ${old_surface}… -> ${new_surface}…, plugin ${old_plugin}… -> ${new_plugin}…"
    # The locale set, derived the way docs/tools/mirror.py derives it (from
    # the tree, not a list hand-copied into this script): every translation
    # that carries a protocol.md beside English's.
    for f in docs/*/reference/protocol.md; do
        loc="$(basename "$(dirname "$(dirname "$f")")")"
        [ "$loc" = en ] && continue
        sed -i \
            -e "s/surface-sha256: ${old_surface}/surface-sha256: ${new_surface}/g" \
            -e "s/sha256:${old_plugin}/sha256:${new_plugin}/g" \
            "$f"
        log "  updated $f"
    done
else
    log "digest unchanged (${new_surface}…) — no translation to touch"
fi

python3 docs/tools/mirror.py >/dev/null
log "mirror.py: all locales still agree with English"

# ---- 8. commit proto + docs, then the UI Kit (which needs a clean tree) ---
#
# Committing first rather than through a temporary commit: sync-ui-kit.mjs's
# cross-repository mode takes an explicit --plugins-ref and refuses to run
# against a tree that is dirty OR at any SHA other than that ref (its whole
# point is pinning the comparison to two named commits, not "whatever is
# checked out"). A temporary commit would need to be either kept (indistinguishable
# from just committing) or undone with a reset (which, after a real commit
# already landed on this branch, risks exactly the branch-state confusion
# `git reset --hard` warnings exist for). Committing for real is the simpler
# of the two and leaves nothing to clean up.
proto_paths=(
    proto/plugin.proto proto/PROTO_VERSION proto/ASTRA_PROTO.lock
    astra-plugin-sdk/proto/plugin.proto
    astra-plugin-sdk-python/astra_plugin_sdk/proto/plugin.proto
    astra-plugin-sdk-python/astra_plugin_sdk/proto/plugin_pb2.py
    astra-plugin-sdk-python/astra_plugin_sdk/proto/plugin_pb2_grpc.py
    astra-plugin-sdk-ts/src/generated
    docs
)
git add -- "${proto_paths[@]}"
proto_commit=""
if [ -n "$(git status --porcelain -- "${proto_paths[@]}")" ]; then
    if [ "$no_commit" = 1 ]; then
        log "--no-commit: proto/docs changes staged for review. Stopping before the commit."
        git status --short -- "${proto_paths[@]}"
        exit 0
    fi
    git commit --quiet -m "$(cat <<EOF
proto: resync against Astra@${astra_sha:0:12}

tools/resync-astra.sh ran the full upstream recipe (slice, vendored
copies, PROTO_VERSION, the Python and TypeScript generated stubs,
ASTRA_PROTO.lock, and the protocol reference docs in every locale)
against this Astra commit. Without this, the vendored copies and the
docs digests drift from a moved protocol one step at a time, and each
drifted file is a separate, unrelated-looking CI failure — which is
how a single upstream resync turned both \`proto (vendored copies)\`
and \`mirror\` red on 2026-11-05 with no comment connecting the two.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01H9xxVvoEHGt2DBkwvVFrRA
EOF
)"
    proto_commit="$(git rev-parse HEAD)"
    log "committed proto+docs resync: ${proto_commit:0:12}"
else
    log "nothing to change: proto and docs already match Astra@${astra_sha:0:12}"
fi

# ---- 8b. command schema: vendor Astra's own generated JSON Schema ---------
#
# astra-core/schemas/portable-command.schema.json is schemars' own reading
# of the exact type the client parses a command into — the shape authority
# spec/content/ingest-v1.md §6 points readers at, and what
# tools/check-content-goldens.py's COMMAND_SCHEMA_TABLE checks every command
# golden against. Nothing on this side regenerates it, only copies it in, so
# without this step a schema that moved upstream would silently stop being
# the client's own types — the same kind of silent drift that let a command
# golden disagree with the real client twice before (AstraPlugins#154).
SCHEMA_SRC="$ASTRA_ROOT/astra-core/schemas/portable-command.schema.json"
SCHEMA_DEST="$REPO_ROOT/spec/content/schemas/portable-command-v1.schema.json"
[ -f "$SCHEMA_SRC" ] || die "$SCHEMA_SRC not found in this Astra checkout — astra-core/schemas moved or was renamed."

schema_commit=""
cp -- "$SCHEMA_SRC" "$SCHEMA_DEST"
git add -- "$SCHEMA_DEST"
if [ -n "$(git status --porcelain -- "$SCHEMA_DEST")" ]; then
    if [ "$no_commit" = 1 ]; then
        log "--no-commit: the portable-command schema changed. Stopping before the commit."
        git status --short -- "$SCHEMA_DEST"
        exit 0
    fi
    git commit --quiet -m "$(cat <<EOF
spec(content): resync the portable-command schema against Astra@${astra_sha:0:12}

astra-core/schemas/portable-command.schema.json moved upstream; nothing
here regenerates it, only tools/resync-astra.sh copies it in, so without
this commit tools/check-content-goldens.py's COMMAND_SCHEMA_TABLE would
go on checking every command golden against a schema that is no longer
the client's own types.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01H9xxVvoEHGt2DBkwvVFrRA
EOF
)"
    schema_commit="$(git rev-parse HEAD)"
    log "committed command schema resync: ${schema_commit:0:12}"
else
    log "nothing to change: the portable-command schema already matches Astra@${astra_sha:0:12}"
fi

ui_kit_commit=""
if [ "$skip_ui_kit" = 1 ]; then
    log "--skip-ui-kit: leaving the UI Kit as already committed"
else
    log "UI Kit: syncing against $ASTRA_ROOT/astra-ui"
    (cd "$ASTRA_ROOT/astra-ui" && bun install --frozen-lockfile >/dev/null)
    plugins_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    node tools/sync-ui-kit.mjs --astra-dir "$ASTRA_ROOT" --astra-ref "$astra_sha" --plugins-ref "$plugins_sha"

    ui_paths=(astra-plugin-ui astra-plugin-cli/vendor/astra-plugin-ui astra-plugin-cli/src/templates/ui_assets.rs)
    git add -- "${ui_paths[@]}"
    if [ -n "$(git status --porcelain -- "${ui_paths[@]}")" ]; then
        if [ "$no_commit" = 1 ]; then
            log "--no-commit: UI Kit changes staged for review. Stopping before the commit."
            git status --short -- "${ui_paths[@]}"
            exit 0
        fi
        git commit --quiet -m "$(cat <<EOF
ui-kit: resync the vendored snapshot against Astra@${astra_sha:0:12}

tools/sync-ui-kit.mjs --check is what the "UI Kit" CI job runs, and it
only ever reports drift — nothing regenerates the vendored snapshot or
the CLI's resource table automatically, so without this commit the next
CI run on this branch would go red over a file nobody here edited.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01H9xxVvoEHGt2DBkwvVFrRA
EOF
)"
        ui_kit_commit="$(git rev-parse HEAD)"
        log "committed UI Kit resync: ${ui_kit_commit:0:12}"
    else
        log "nothing to change: UI Kit already matches Astra@${astra_sha:0:12}"
    fi
fi

# ---- 9. final checks -------------------------------------------------------
log "final checks:"
bash tools/check-proto.sh
bash tools/gen-proto-lock.sh --astra-dir "$ASTRA_ROOT" --check
python3 tools/check-protocol-counts.py
if [ "$skip_docgen_check" = 1 ]; then
    log "--skip-docgen-check: not building astra-plugin-cli or running docgen --check"
else
    log "building astra-plugin-cli --release (docgen --check reads its clap definitions)"
    cargo build --quiet --release --manifest-path astra-plugin-cli/Cargo.toml
    ASTRA_PLUGIN_BIN="$CARGO_TARGET_DIR/release/astra-plugin" python3 tools/docgen/gen.py --check
fi
python3 docs/tools/mirror.py >/dev/null
log "mirror.py: ok (re-checked post-commit)"
python3 tools/check-content-goldens.py >/dev/null
log "check-content-goldens.py: ok (every command golden still parses against the resynced schema)"

# ---- 10. summary ------------------------------------------------------------
echo
echo "resync-astra: summary"
echo "  Astra followed:    ${astra_sha:0:12}"
echo "  surface-sha256:    ${old_surface}… -> ${new_surface}…"
echo "  plugin sha256:     ${old_plugin}… -> ${new_plugin}…"
if [ -n "$proto_commit" ]; then
    echo "  proto+docs commit: $proto_commit"
else
    echo "  proto+docs commit: none (no change)"
fi
if [ -n "$schema_commit" ]; then
    echo "  command schema commit: $schema_commit"
else
    echo "  command schema commit: none (no change)"
fi
if [ "$skip_ui_kit" = 1 ]; then
    echo "  UI Kit commit:     skipped (--skip-ui-kit)"
elif [ -n "$ui_kit_commit" ]; then
    echo "  UI Kit commit:     $ui_kit_commit"
else
    echo "  UI Kit commit:     none (no change)"
fi
if [ -z "$proto_commit" ] && [ -z "$schema_commit" ] && [ -z "$ui_kit_commit" ]; then
    echo "resync-astra: nothing to change."
fi
