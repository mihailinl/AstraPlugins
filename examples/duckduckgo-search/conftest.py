"""Make `src.plugin` and `src.ddg` importable from `tests/`.

`plugin.toml` runs the plugin as `python -u -m src.plugin` from the bundle
root, so the bundle root is what has to be on `sys.path` — the same path the
daemon gives it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
