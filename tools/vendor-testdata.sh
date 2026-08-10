#!/usr/bin/env bash
# Vendor `testdata/bundles/` into the two repositories that consume it.
#
#   tools/vendor-testdata.sh            # copy, then verify every copy
#   tools/vendor-testdata.sh --check    # verify only; never writes. CI runs this.
#
# ── why a copy at all ──────────────────────────────────────────────────────
#
# Three implementations of one bundle format live in three repositories that
# release on three schedules, and the only thing keeping them honest is that
# they answer the same questions about the same bytes. A shared directory is
# the cheapest way to make "the same bytes" true; a *symlink* to a sibling
# checkout is the cheapest way to make it accidentally false, because CI for
# `Astra` clones `Astra` and nothing else, and a suite that silently skips when
# its fixtures are missing is a suite that passes forever.
#
# So each consumer holds a copy, and each copy is verified against
# `SHA256SUMS` — by this script, and again by that repo's own test suite at run
# time. The canonical directory is here, in AstraPlugins, next to the packer
# that defines the format. Editing a vendored copy is the mistake this guards
# against: it is caught the moment `--check` runs, and named as a drift rather
# than reported as a mysterious digest failure.
#
# ── where the copies go ────────────────────────────────────────────────────
#
#   Astra          astra-rs/astra-daemon/testdata/bundles/
#   astra-registry tests/vectors/
#
# Both repos are found beside this one by default. Override with
# `ASTRA_REPO=/path` and `ASTRA_REGISTRY_REPO=/path`; a repo that is not present
# is reported and skipped, not treated as a failure, so this script is usable
# from a checkout of AstraPlugins alone.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
src="$here/testdata/bundles"
siblings="$(cd -- "$here/.." && pwd)"

astra_repo="${ASTRA_REPO:-$siblings/Astra}"
registry_repo="${ASTRA_REGISTRY_REPO:-$siblings/astra-registry}"

astra_dest="$astra_repo/astra-rs/astra-daemon/testdata/bundles"
registry_dest="$registry_repo/tests/vectors"

check_only=0
case "${1:-}" in
  --check) check_only=1 ;;
  "") ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

if [ ! -f "$src/SHA256SUMS" ]; then
  echo "FAIL  $src/SHA256SUMS is missing — run: node testdata/bundles/generate.mjs" >&2
  exit 1
fi

# The files a consumer gets. Deliberately NOT the whole directory: the
# generator, its ZIP writer and handcheck.sh are how the goldens are produced
# and re-derived, and neither belongs in a repo that only reads them.
manifest_files="$(cut -c67- "$src/SHA256SUMS")"

fail=0
note() { printf '%s\n' "$*"; }

# The canonical directory first. If it does not agree with its own sums file
# there is nothing worth copying, and a stale golden vendored into two repos is
# strictly worse than one that is only wrong here.
note "canonical  $src"
if ! (cd "$src" && sha256sum -c SHA256SUMS >/dev/null 2>&1); then
  note "FAIL       testdata/bundles does not match its own SHA256SUMS."
  note "           A golden was edited without regenerating, or SHA256SUMS is stale."
  note "           Run: node testdata/bundles/generate.mjs"
  (cd "$src" && sha256sum -c SHA256SUMS 2>&1 | grep -v ': OK$' || true)
  exit 1
fi
note "ok         $(printf '%s\n' "$manifest_files" | wc -l) files match SHA256SUMS"

vendor_one() { # label repo dest
  local label="$1" repo="$2" dest="$3"
  if [ ! -d "$repo" ]; then
    note ""
    note "skip       $label not found at $repo (set ${label^^}_REPO to override)"
    return 0
  fi

  note ""
  note "$label"
  note "           $dest"

  if [ "$check_only" = 0 ]; then
    mkdir -p "$dest"
    # Copy the listed files and SHA256SUMS, then delete anything else that is
    # in the destination. A leftover vector from a deleted case would otherwise
    # sit there being consumed by a suite that iterates the directory.
    printf '%s\n' "$manifest_files" | while IFS= read -r f; do
      cp -f "$src/$f" "$dest/$f"
    done
    cp -f "$src/SHA256SUMS" "$dest/SHA256SUMS"
    cp -f "$src/README.md" "$dest/README.md" 2>/dev/null || true
    for existing in "$dest"/*; do
      [ -e "$existing" ] || continue
      local base
      base="$(basename "$existing")"
      case "$base" in
        SHA256SUMS|README.md) continue ;;
      esac
      if ! printf '%s\n' "$manifest_files" | grep -qxF "$base"; then
        note "           removing stale $base"
        rm -f "$existing"
      fi
    done
  fi

  if [ ! -f "$dest/SHA256SUMS" ]; then
    note "FAIL       no vendored copy at $dest — run $0 without --check"
    fail=1
    return 0
  fi
  if ! cmp -s "$src/SHA256SUMS" "$dest/SHA256SUMS"; then
    note "FAIL       the vendored SHA256SUMS differs from the canonical one."
    note "           testdata/bundles changed and this copy was not refreshed."
    note "           Run: $0"
    fail=1
    return 0
  fi
  if ! (cd "$dest" && sha256sum -c SHA256SUMS >/dev/null 2>&1); then
    note "FAIL       a vendored file does not match SHA256SUMS — the copy was edited:"
    (cd "$dest" && sha256sum -c SHA256SUMS 2>&1 | grep -v ': OK$' | sed 's/^/           /' || true)
    fail=1
    return 0
  fi
  note "ok         vendored copy matches the canonical digests"
}

vendor_one astra "$astra_repo" "$astra_dest"
vendor_one astra_registry "$registry_repo" "$registry_dest"

note ""
if [ "$fail" != 0 ]; then
  note "FAILED — the shared test vectors have drifted."
  note "A digest that differs between repositories is precisely the condition these"
  note "vectors exist to make impossible, so this is a hard failure, never a warning."
  exit 1
fi
note "OK — every copy of testdata/bundles agrees, byte for byte."
