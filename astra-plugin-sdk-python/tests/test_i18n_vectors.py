"""`I18n`, held to `testdata/i18n/vectors.json` — the same file the other two SDKs read.

`I18n` shipped in three languages and had never had a test. It disagreed with
itself three ways, silently, and this SDK owned one of the three: its lookup was
an ``or`` chain, so ``""`` — the only way to blank a string in one locale — read
as "not translated" and fell through to English.

A per-SDK test would have pinned each implementation to itself. This one reads
the shared vectors, so the question it answers is not "does Python still do what
Python did" but "do the three still do the same thing". Coupling C17; the other
half is ``tools/gen-i18n.mjs``, which generates the plural tables from
``spec/i18n.yaml`` so they cannot be three hand-written copies.

The floors below come first, on purpose. A vectors file that failed to load, or
that somebody emptied, must fail as that and not pass as a clean run.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from astra_plugin_sdk import plural
from astra_plugin_sdk.i18n import I18n, key

#: `testdata/` sits at the repository root, two levels up from this file. It is
#: not shipped inside the wheel — these vectors are shared with the Rust and
#: TypeScript SDKs and with nothing that installs this package — so a run from a
#: checkout is the only run that can execute them.
VECTORS = pathlib.Path(__file__).resolve().parents[2] / "testdata" / "i18n" / "vectors.json"

#: Floors, not counts. Each is well under what the file carries today, so
#: adding a case is free and losing most of them is not. Written before the
#: mutation that proved this test can fail, which is the only order in which a
#: floor means anything.
MIN_FIXTURES = 5
MIN_LOADS = 5
MIN_CASES = 30
MIN_PLURAL = 35


def _vectors() -> dict:
    if not VECTORS.is_file():
        pytest.fail(
            f"{VECTORS} is missing. This test proves the three SDKs agree about "
            "i18n; without the shared vectors it proves nothing, so it fails "
            "rather than skipping."
        )
    return json.loads(VECTORS.read_text(encoding="utf-8"))


VECTOR_DOC = _vectors()


def test_the_vector_file_is_the_one_this_test_was_written_against():
    """The floor. Everything below is vacuous if this is not true."""
    assert VECTOR_DOC["schema"] == "astra.i18n.vectors/1", (
        "the vectors file changed shape; this reader has not. "
        f"schema={VECTOR_DOC.get('schema')!r}"
    )
    assert len(VECTOR_DOC["fixtures"]) >= MIN_FIXTURES, (
        f"{len(VECTOR_DOC['fixtures'])} fixture(s), floor is {MIN_FIXTURES}"
    )
    assert len(VECTOR_DOC["loads"]) >= MIN_LOADS, (
        f"{len(VECTOR_DOC['loads'])} load vector(s), floor is {MIN_LOADS}"
    )
    assert len(VECTOR_DOC["cases"]) >= MIN_CASES, (
        f"{len(VECTOR_DOC['cases'])} case(s), floor is {MIN_CASES}"
    )
    assert len(VECTOR_DOC["plural"]) >= MIN_PLURAL, (
        f"{len(VECTOR_DOC['plural'])} plural vector(s), floor is {MIN_PLURAL}"
    )


def _materialise(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    """Write a fixture's files into a directory of its own and return it."""
    if name == "MISSING":
        return tmp_path / "never-created"
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    for filename, text in VECTOR_DOC["fixtures"][name]["files"].items():
        (directory / filename).write_text(text, encoding="utf-8")
    return directory


@pytest.mark.parametrize("vector", VECTOR_DOC["loads"], ids=lambda v: v["name"])
def test_loading_a_fixture(tmp_path, vector):
    i18n = I18n(_materialise(tmp_path, vector["fixture"]))

    assert i18n.available_languages == vector["languages"], vector["name"]
    errors = i18n.load_errors
    assert len(errors) == vector["error_count"], (
        f"{vector['name']}: expected {vector['error_count']} load error(s), got "
        f"{len(errors)}: {errors}"
    )
    blob = "\n".join(errors)
    for needle in vector["errors_contain"]:
        assert needle in blob, f"{vector['name']}: no load error mentions {needle!r}: {errors}"


@pytest.mark.parametrize("case", VECTOR_DOC["cases"], ids=lambda c: c["name"])
def test_one_call(tmp_path, case):
    i18n = I18n(_materialise(tmp_path, case["fixture"]))
    i18n.set_language(case["language"])

    call = case["call"]
    if call == "t":
        got = i18n.t(case["key"])
    elif call == "has":
        got = i18n.has(case["key"])
    elif call == "tf":
        got = i18n.tf(case["key"], *case["args"])
    elif call == "ta":
        got = i18n.ta(case["key"], **case["named"])
    elif call == "tn":
        got = i18n.tn(case["key"], case["n"], **case["named"])
    elif call == "count_prefixed":
        got = i18n.count_prefixed(case["key"])
    elif call == "key":
        got = key(case["key"])
    else:  # pragma: no cover — a vector this reader does not implement
        pytest.fail(
            f"{case['name']}: the vectors use a call this test does not implement: "
            f"{call!r}. Implement it here rather than dropping the case, or the "
            "vector is carried by two SDKs and not by three."
        )

    assert got == case["expect"], case["name"]


@pytest.mark.parametrize(
    "vector", VECTOR_DOC["plural"], ids=lambda v: f"{v['language']}-{v['n']}"
)
def test_plural_category(vector):
    assert plural.category(vector["language"], vector["n"]) == vector["expect"]


def test_every_declared_language_ends_in_other():
    """The terminal category, asserted where an SDK author would look for it.

    `tn` falls back `<key>.<category>` -> `<key>.other` -> `<key>`, so a
    language whose table did not end in `other` would have counts that resolve
    to nothing at all.
    """
    assert len(plural.CATEGORIES) >= 2, (
        f"the generated table holds {len(plural.CATEGORIES)} language(s) — that is a "
        "broken generator, not a shrunken vocabulary"
    )
    for lang, categories in plural.CATEGORIES.items():
        assert categories[-1] == "other", f"{lang} ends in {categories[-1]!r}"
        assert plural.is_declared(lang)
    assert not plural.is_declared("zh-CN")
