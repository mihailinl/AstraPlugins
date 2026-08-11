"""Make `src.plugin` importable from `tests/`.

`plugin.toml` runs the plugin as `python -m src.plugin` from the bundle root, so
the bundle root is what has to be on `sys.path` — the same path the daemon gives
it. Doing it here rather than with a `[tool.pytest.ini_options] pythonpath`
keeps the file that explains it next to the thing it explains.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
