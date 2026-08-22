#!/usr/bin/env python3
"""Which languages `docs/` is translated into. One declaration, three readers.

`mirror.py`, `doctest.py` and the `couplings` job's C6 scan each used to carry
their own copy of this tuple, and `mirror.py`'s comment claimed to be "where
that decision is recorded" while two other files recorded it as well. All three
spelled Chinese `zh-CN`, which is not a language Astra can be set to and never
was: an author who mirrored the directory name into `locales/zh-CN.json` would
have shipped a file that is packed, digested, signed and read by nothing.

So this is the declaration, and C14 in the `couplings` job holds it to two
things at once:

* every code here is a code in `spec/locales.yaml` — the ten the daemon can
  actually send — so a docs directory can never teach an author a spelling that
  does not exist; and
* the set of directories actually under `docs/` is exactly this tuple, so a
  `docs/fr` added without a line here fails instead of being silently invisible
  to `mirror.py` and `doctest.py` — which is what a stray locale directory is
  today: `linkcheck.py` walks it, and nothing else knows it is there.

A NEW LOCALE IS NOT PICKED UP AUTOMATICALLY. This is deliberate and it is the
whole point of a literal tuple: adding one is a decision to keep it mirroring
`docs/en` page for page, sample for sample, forever. Deriving this list from
`ls docs/` would make that decision by accident and would make C14 vacuous — it
would be comparing the directory listing with itself.

This is a PROPER SUBSET of `spec/locales.yaml` and it is allowed to stay one.
Three different subsets of those ten codes exist in this system: the ten Astra
accepts, the three whose Astra UI translation is held complete (`maintained` in
that file), and these seven. None of them implies another.
"""

from __future__ import annotations

#: Every locale directory under `docs/`. `en` is authoritative and is first;
#: the rest are file-for-file mirrors of it.
LOCALES = ("en", "de", "es", "ja", "ru", "uk", "zh")

#: The mirrors alone — `LOCALES` without the language they mirror. `mirror.py`
#: iterates this; `doctest.py` runs samples in all of `LOCALES`, English
#: included.
TRANSLATIONS = tuple(code for code in LOCALES if code != "en")
