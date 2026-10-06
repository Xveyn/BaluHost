"""The one rule for what a plugin name may look like.

A plugin name ends up in filesystem paths (``plugins_dir / name``), module
names (``app.plugins.installed.<name>``) and a root-run spawn wrapper. Before
this module only that wrapper (``deploy/install/bin/spawn-plugin-worker.sh``)
enforced a character set; the Python side built paths from the raw URL segment,
so ``..`` reached ``shutil.rmtree`` (marketplace uninstall) and the manager's
load fallback (#634).

Keep this in step with the wrapper's ``^[a-z0-9_]+$``: a name accepted here but
refused there would install fine and then never start. The length cap is the
only addition.
"""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import Path as PathParam

_NAME_CORE = r"[a-z0-9_]{1,64}"

#: For ``Path(..., pattern=...)`` / pydantic ``Field(pattern=...)``.
PLUGIN_NAME_PATTERN = rf"^{_NAME_CORE}$"

_PLUGIN_NAME_RE = re.compile(_NAME_CORE)


def is_valid_plugin_name(name: object) -> bool:
    """True if *name* is a safe plugin name.

    ``fullmatch`` rather than ``match(..., "$")``: ``$`` also matches before a
    trailing newline, which would let ``"demo\\n"`` through.
    """
    return isinstance(name, str) and _PLUGIN_NAME_RE.fullmatch(name) is not None


#: A plugin name taken from a URL segment. Routes that build a path from it
#: (load fallback, uninstall, asset serving) must not see "..", "a/b" or "";
#: FastAPI answers 422 before the handler runs (#634). Lives here and not in
#: ``api/deps.py``: importing this module runs ``app/plugins/__init__.py``, and
#: the base dependency module should not pull in the plugin package.
PluginNameParam = Annotated[
    str,
    PathParam(
        pattern=PLUGIN_NAME_PATTERN,
        description="Plugin name: lowercase letters, digits, underscore",
    ),
]
