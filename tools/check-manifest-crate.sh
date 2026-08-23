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
#   tools/check-manifest-crate.sh                  # exit 0 if in sync, 1 otherwise
#   tools/check-manifest-crate.sh --sync           # copy upstream over the vendored copy
#   tools/check-manifest-crate.sh --ref <ref>      # compare against that git ref
#   ASTRA_REF=worktree tools/check-manifest-crate.sh   # compare against the checkout as it is
#
# WHICH TREE IS "UPSTREAM", and why this is not the checkout you have.
#
# This script used to read whatever was in `$ASTRA_REPO`'s working tree. That is
# not a source of truth, it is a desk. On 2026-08-22 the local Astra checkout was
# on `main` at ef4bb0e8, two commits behind `origin/main` at c62e2536, and this
# script therefore said `src/lib.rs` and `src/platform.rs` had DRIFTED and told
# the reader to run `--sync`, "upstream wins; edit Astra's copy, never this one".
#
# The vendored copy was byte-identical to `origin/main`. It was AHEAD, not
# behind: c62e2536 had added `NOARCH_PLATFORM_KEY` and its doc comment, somebody
# had vendored that, and the checkout had not been fetched since. Running the
# advice would have deleted a real constant — and the constant's own doc says
# three places have to agree about it, so the deletion would have been silent
# here and loud somewhere else, later.
#
# So the comparison is against a ref this script can NAME, resolved out of the
# Astra repository's git database rather than out of its index or its worktree:
#
#   * `$ASTRA_REF`, default `origin/main`. Files are read with `git show`, so
#     what the checkout happens to have open is irrelevant.
#   * If that ref does not resolve, the script REFUSES rather than falling back
#     to the worktree. A comparison against a tree nobody can name is not a
#     comparison — it is the failure above, with the evidence removed.
#   * `ASTRA_REF=worktree` is the deliberate escape hatch, for an Astra engineer
#     editing the crate before pushing it. It prints the branch, the sha, how far
#     that sits from `origin/main` and whether the tree is dirty, because a mode
#     that reads an unpublished tree has to say so every time.
#
# In CI this changes nothing: the `proto-upstream` job checks out Astra fresh at
# a named ref, so `origin/main` and the worktree are the same bytes. It changes
# everything on a maintainer's machine, which is the only place the bug lived.
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
    "src/permissions.rs"
    "src/platform.rs"
    "README.md"
)

# A dependency present upstream and deliberately absent here. See the header.
UPSTREAM_ONLY_DEPS=("astra-core")

# The floor for the `src/*.rs` scan in section 3. Five modules upstream today,
# and every one of them is in IDENTICAL. Written before the scan, not after it:
# `find src -type f -name '*.rs'` whose pattern or path has moved returns
# nothing, and an empty enumeration passes section 3 in perfect silence while
# reading as coverage — section 3 only ever reports files it FOUND.
MIN_SRC_FILES=5

VENDORED="$REPO_ROOT/astra-plugin-cli/vendor/astra-plugin-manifest"

# Where Astra is checked out. Sibling of this repository unless told otherwise.
ASTRA_REPO="${ASTRA_REPO:-$(cd -- "$REPO_ROOT/.." && pwd)/Astra}"
# The crate's path INSIDE that repository, at whatever ref we end up reading.
UPSTREAM_REL="astra-rs/astra-plugin-manifest"
ASTRA_REF="${ASTRA_REF:-origin/main}"

SYNC_CMD="tools/check-manifest-crate.sh --sync"

mode="check"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --sync) mode="sync"; shift ;;
        --ref)
            if [ -z "${2:-}" ]; then
                printf 'check-manifest-crate: --ref needs a git ref (or the word `worktree`).\n' >&2
                exit 2
            fi
            ASTRA_REF="$2"; shift 2 ;;
        --ref=*) ASTRA_REF="${1#--ref=}"; shift ;;
        *)
            printf 'check-manifest-crate: unknown argument %s\n' "$1" >&2
            printf '                           expected --sync, --ref <ref>, or nothing.\n' >&2
            exit 2 ;;
    esac
done

TMPROOT="$(mktemp -d)"
trap 'rm -rf -- "$TMPROOT"' EXIT
third_tmp="$TMPROOT/third"

failures=0
# Failures `--sync` would make WORSE, counted apart from the rest so the summary
# at the bottom cannot recommend it over the top of a message saying not to.
wrong_tree_failures=0

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

if [ ! -d "$ASTRA_REPO/$UPSTREAM_REL" ]; then
    printf 'check-manifest-crate: SKIP the Astra checkout is not at %s.\n' "$ASTRA_REPO"
    printf '                           `plugin.toml` is defined in Astra and vendored here; without\n'
    printf '                           that checkout there is nothing to compare against. Set\n'
    printf '                           ASTRA_REPO=/path/to/Astra to run this check.\n'
    exit 0
fi

# ---- 0b. name the tree being compared against -------------------------------
#
# Everything below reads `$UPSTREAM`. The only question this section answers is
# WHICH bytes that directory holds, and the answer is printed either way, because
# the whole defect this section exists for was a comparison whose input nobody
# had looked at. See the header.
WORKTREE_CRATE="$ASTRA_REPO/$UPSTREAM_REL"

git_astra() { git -C "$ASTRA_REPO" "$@"; }

astra_is_git=0
if git_astra rev-parse --git-dir >/dev/null 2>&1; then
    astra_is_git=1
fi

# A one-line description of what the vendored copy is being held against. It is
# printed on success and quoted in every failure, so a reader never has to guess.
UPSTREAM_DESC=""

if [ "$ASTRA_REF" = "worktree" ]; then
    # The escape hatch. Legitimate — an Astra engineer edits the crate, syncs it
    # here, and pushes both — and it reads bytes that exist nowhere but that
    # machine, so it describes itself in full every single time.
    UPSTREAM="$WORKTREE_CRATE"
    if [ "$astra_is_git" -eq 1 ]; then
        head_sha="$(git_astra rev-parse --short HEAD 2>/dev/null || echo '?')"
        head_ref="$(git_astra rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
        dirty="clean"
        if ! git_astra diff --quiet -- "$UPSTREAM_REL" 2>/dev/null; then
            dirty="UNCOMMITTED CHANGES to $UPSTREAM_REL"
        fi
        drift=""
        if git_astra rev-parse --verify --quiet 'origin/main^{commit}' >/dev/null 2>&1; then
            behind="$(git_astra rev-list --count 'HEAD..origin/main' 2>/dev/null || echo '?')"
            ahead="$(git_astra rev-list --count 'origin/main..HEAD' 2>/dev/null || echo '?')"
            drift=", $behind behind / $ahead ahead of origin/main"
        else
            drift=", and origin/main does not resolve — this checkout has no fetched upstream"
        fi
        UPSTREAM_DESC="the WORKING TREE of $ASTRA_REPO (HEAD $head_sha on $head_ref$drift, $dirty)"
    else
        UPSTREAM_DESC="the WORKING TREE of $ASTRA_REPO (not a git repository — the bytes cannot be named at all)"
    fi
    printf 'check-manifest-crate: comparing against %s\n' "$UPSTREAM_DESC"
    printf '                           ASTRA_REF=worktree was asked for. These bytes may exist\n'
    printf '                           on no other machine; a green run here proves nothing about\n'
    printf '                           what Astra has published.\n'
else
    if [ "$astra_is_git" -eq 0 ]; then
        printf 'check-manifest-crate: FAIL %s is not a git repository.\n' "$ASTRA_REPO" >&2
        printf '                           This check compares the vendored crate against a NAMED ref\n' >&2
        printf '                           (%s), not against whatever a directory happens to hold —\n' "$ASTRA_REF" >&2
        printf '                           a comparison against a tree nobody can name is not a\n' >&2
        printf '                           comparison. Point ASTRA_REPO at a real clone, or ask for\n' >&2
        printf '                           the unnamed tree on purpose with ASTRA_REF=worktree.\n' >&2
        exit 1
    fi
    if ! ref_sha="$(git_astra rev-parse --verify --quiet "$ASTRA_REF^{commit}")"; then
        printf 'check-manifest-crate: FAIL %s does not resolve in %s.\n' "$ASTRA_REF" "$ASTRA_REPO" >&2
        printf '                           Refusing rather than falling back to the working tree: that\n' >&2
        printf '                           fallback is the defect this argument exists to remove (see the\n' >&2
        printf '                           header — it once advised deleting NOARCH_PLATFORM_KEY).\n' >&2
        printf '                           fix:  git -C %s fetch origin\n' "$ASTRA_REPO" >&2
        printf '                           or:   ASTRA_REF=<a ref that exists> tools/check-manifest-crate.sh\n' >&2
        printf '                           or:   ASTRA_REF=worktree, to compare the checkout as it is\n' >&2
        exit 1
    fi

    # Materialised from the object database, so the index, the worktree and the
    # branch the checkout sits on are all out of the picture.
    UPSTREAM="$TMPROOT/upstream"
    mkdir -p -- "$UPSTREAM"

    # The WHOLE crate, not just the files in IDENTICAL. Section 3 asks "is there
    # a module upstream that nobody added to IDENTICAL?", and materialising only
    # the declared files would answer that question by construction — a check
    # whose reach shrank to exactly what it already knew about.
    tracked="$(git_astra ls-tree -r --name-only "$ref_sha" -- "$UPSTREAM_REL/" || true)"
    if [ -z "$tracked" ]; then
        printf 'check-manifest-crate: FAIL %s carries no %s.\n' "$ASTRA_REF" "$UPSTREAM_REL" >&2
        printf '                           Either the crate moved upstream (re-point UPSTREAM_REL) or\n' >&2
        printf '                           this ref predates it.\n' >&2
        exit 1
    fi
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        rel="${path#"$UPSTREAM_REL"/}"
        mkdir -p -- "$(dirname -- "$UPSTREAM/$rel")"
        git_astra show "$ref_sha:$path" > "$UPSTREAM/$rel"
    done <<EOF
$tracked
EOF

    subject="$(git_astra log -1 --format=%s "$ref_sha" 2>/dev/null || true)"
    UPSTREAM_DESC="$ASTRA_REPO @ $ASTRA_REF ($(git_astra rev-parse --short "$ref_sha") ${subject:0:60})"
    printf 'check-manifest-crate: comparing against %s\n' "$UPSTREAM_DESC"

    # Informational, and it is the line that would have saved the afternoon this
    # header describes: the checkout is not at the ref, so anything the reader
    # sees in their editor is NOT what is being compared, in either direction.
    head_sha="$(git_astra rev-parse HEAD 2>/dev/null || echo '')"
    if [ -n "$head_sha" ] && [ "$head_sha" != "$ref_sha" ]; then
        behind="$(git_astra rev-list --count "HEAD..$ref_sha" 2>/dev/null || echo '?')"
        ahead="$(git_astra rev-list --count "$ref_sha..HEAD" 2>/dev/null || echo '?')"
        printf '                           note: that checkout is on %s (%s), %s behind / %s ahead of %s.\n' \
            "$(git_astra rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')" \
            "$(git_astra rev-parse --short HEAD)" "$behind" "$ahead" "$ASTRA_REF"
        printf '                           Its working tree is NOT what was compared.\n'
    fi
fi

# ---- 1. sync mode: copy, then fall through and verify -----------------------
if [ "$mode" = "sync" ]; then
    printf 'check-manifest-crate: syncing %s -> %s\n' "$UPSTREAM_DESC" "$VENDORED"
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

# ---- 1b. the third tree, for telling the two failure directions apart --------
#
# See the block inside section 2. `third_bytes <rel> <outfile>` writes the third
# tree's copy of <rel> and returns 0, or returns non-zero when there is no third
# tree to consult — in which case section 2 falls through to the generic message,
# which is the correct behaviour rather than a silent one.
THIRD_DESC=""
THIRD_FIX=()

if [ "$ASTRA_REF" = "worktree" ]; then
    # Comparing an unpublished tree. The third opinion is the published one, and
    # "the vendored copy already matches origin/main" is precisely the state in
    # which `--sync` deletes something real.
    if [ "$astra_is_git" -eq 1 ] \
        && third_sha="$(git_astra rev-parse --verify --quiet 'origin/main^{commit}')"; then
        THIRD_DESC="origin/main ($(git_astra rev-parse --short "$third_sha"))"
        THIRD_FIX=(
            "Your checkout is not at origin/main, and the vendored copy already agrees with"
            "origin/main. It is the CHECKOUT that is out of date here, not this repository."
            "fix:  git -C '$ASTRA_REPO' fetch origin && git -C '$ASTRA_REPO' status"
            "or:   drop ASTRA_REF=worktree and let this script read origin/main directly"
        )
        third_bytes() {
            git_astra show "$third_sha:$UPSTREAM_REL/$1" > "$2" 2>/dev/null
        }
    else
        third_bytes() { return 1; }
    fi
else
    # Comparing a named ref. The third opinion is the desk: bytes that are only
    # on this machine, which is how a vendored copy comes to be AHEAD of the ref.
    THIRD_DESC="your Astra checkout's working tree ($(git_astra rev-parse --short HEAD 2>/dev/null || echo '?') on $(git_astra rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"
    THIRD_FIX=(
        "fix:  git -C '$ASTRA_REPO' fetch origin      (if that checkout is simply behind)"
        "or:   push the Astra change so $ASTRA_REF carries it, then re-run"
        "or:   ASTRA_REF=worktree, if comparing against the unpublished tree is what you meant"
        "diff: git -C '$ASTRA_REPO' diff $ASTRA_REF -- '$UPSTREAM_REL/'"
    )
    third_bytes() {
        [ -f "$WORKTREE_CRATE/$1" ] || return 1
        cp -- "$WORKTREE_CRATE/$1" "$2"
    }
fi

# ---- 2. every shared file is byte-identical ---------------------------------
for rel in "${IDENTICAL[@]}"; do
    up="$UPSTREAM/$rel"
    ven="$VENDORED/$rel"
    if [ ! -f "$up" ]; then
        fail "upstream is missing $rel." \
            "The source of truth is $UPSTREAM_DESC." \
            "A file deleted upstream must be deleted here and dropped from IDENTICAL in this script."
        continue
    fi
    if [ ! -f "$ven" ]; then
        fail "the vendored copy is missing $rel." "Run \`$SYNC_CMD\`."
        continue
    fi
    if cmp -s -- "$up" "$ven"; then
        ok "$rel is byte-identical to Astra's"
        continue
    fi

    # A difference, and there are TWO of them with OPPOSITE fixes. Saying
    # "upstream wins, run --sync" for both is what made this script's advice
    # destructive: on 2026-08-22 the vendored copy was AHEAD of a stale checkout,
    # and `--sync` would have deleted NOARCH_PLATFORM_KEY.
    #
    # They are told apart by a THIRD tree — the one this run is not comparing
    # against. If the vendored bytes match it exactly, nobody edited anything
    # here: the vendored copy is a faithful mirror of some other commit of the
    # upstream crate, and overwriting it destroys work rather than restoring it.
    #
    #   ref mode       third tree = the checkout's working tree
    #   worktree mode  third tree = origin/main
    #
    # Both directions matter, and the second is the one that bit. `--sync` is
    # only ever the right answer when the vendored copy matches NEITHER.
    if third_bytes "$rel" "$third_tmp" && cmp -s -- "$third_tmp" "$ven"; then
        fail "$rel differs from $UPSTREAM_DESC, but matches $THIRD_DESC." \
            "Nothing was edited in this repository. The vendored copy is a faithful" \
            "mirror of $THIRD_DESC — so this is two upstream trees disagreeing, not" \
            "drift here." \
            "DO NOT run --sync: it would overwrite bytes that are not stale, and this" \
            "script has already handed that advice out once over a constant that only" \
            "existed on one side." \
            "${THIRD_FIX[@]}"
        wrong_tree_failures=$((wrong_tree_failures + 1))
        continue
    fi

    # The hint has to name a command that still works after this script exits.
    # In ref mode `$up` is a temp file the EXIT trap is about to delete, so the
    # hint reads the ref back out of git instead.
    if [ "$ASTRA_REF" = "worktree" ]; then
        diff_hint="diff -u '$WORKTREE_CRATE/$rel' '$ven'"
    else
        diff_hint="git -C '$ASTRA_REPO' show '$ASTRA_REF:$UPSTREAM_REL/$rel' | diff -u - '$ven'"
    fi
    fail "$rel has drifted from Astra's copy." \
        "The daemon and the CLI would parse the same plugin.toml differently — that is" \
        "the defect this crate exists to prevent, not a formatting nit." \
        "Compared against $UPSTREAM_DESC." \
        "diff: $diff_hint" \
        "fix:  $SYNC_CMD   (upstream wins; edit Astra's copy, never this one)"
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
    # `|| true` so a missing src/ reaches the floor below as a count of zero and
    # is reported, rather than killing the script with find's own message.
    actual="$(list_src "$side" 2>/dev/null || true)"

    # THE FLOOR, and it is not decoration. This section's only failure is "the
    # scan found a file the declaration does not mention", so a scan that finds
    # NOTHING reports nothing and exits 0 — indistinguishable from a clean bill
    # of health. That is the shape dev/couplings.md gap 7 is about, and it is
    # newly reachable here: `$UPSTREAM` is now a directory this script populates
    # itself, so a wrong path or a half-written materialisation lands as silence
    # rather than as an error.
    found=0
    [ -n "$actual" ] && found="$(printf '%s\n' "$actual" | grep -c '.')"
    if [ "$found" -lt "$MIN_SRC_FILES" ]; then
        fail "the SCAN broke, not the rule: $side holds $found src/*.rs file(s)." \
            "The floor is $MIN_SRC_FILES, which is how many the crate had when this check was" \
            "written. Below it, nothing has been verified — this section only ever" \
            "reports files it FOUND, so finding none reads exactly like finding no" \
            "problem. Either the crate genuinely shrank (lower MIN_SRC_FILES in the" \
            "same commit that deletes the module) or this scan is looking at the" \
            "wrong tree."
        continue
    fi

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
    if [ "$wrong_tree_failures" -eq "$failures" ]; then
        # Every failure was "the vendored copy matches a DIFFERENT upstream tree".
        # `--sync` is the wrong instruction for all of them, and this line used to
        # print it anyway, unconditionally, under every failure there is.
        printf '\ncheck-manifest-crate: %d check(s) failed, and NONE of them is fixed by --sync.\n' \
            "$failures" >&2
        printf '                           The vendored copy is not the odd one out; two upstream trees\n' >&2
        printf '                           disagree. Reconcile those first — each failure above says how.\n\n' >&2
    else
        printf '\ncheck-manifest-crate: %d check(s) failed, %d of them fixed by:\n\n    %s\n\n' \
            "$failures" "$((failures - wrong_tree_failures))" "$SYNC_CMD" >&2
        if [ "$wrong_tree_failures" -ne 0 ]; then
            printf '                           %d is NOT, and says DO NOT run --sync. Read it first.\n\n' \
                "$wrong_tree_failures" >&2
        fi
    fi
    exit 1
fi

printf 'check-manifest-crate: one plugin.toml definition, %d file(s) in sync with %s.\n' \
    "${#IDENTICAL[@]}" "$UPSTREAM_DESC"
