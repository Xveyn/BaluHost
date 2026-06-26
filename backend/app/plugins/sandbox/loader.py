"""Load an external plugin's entrypoint INSIDE the worker process.

exec_module happens here and nowhere else — never in the host. The loaded
module must expose ``register(host)``.
"""
import importlib.util
import os

from app.plugins.sandbox.sdk import PluginHost


class PluginLoadError(Exception):
    """Raised when the plugin entrypoint is missing or has no register()."""


def load_plugin(plugin_dir: str, entrypoint: str, plugin_name: str) -> PluginHost:
    path = os.path.join(plugin_dir, entrypoint)
    if not os.path.isfile(path):
        raise PluginLoadError(f"entrypoint not found: {path}")
    module_name = f"baluhost_sandbox_plugin_{plugin_name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # plugin module-level code blew up
        raise PluginLoadError(f"plugin import failed: {exc}") from exc
    register = getattr(module, "register", None)
    if not callable(register):
        raise PluginLoadError("plugin entrypoint defines no register(host)")
    host = PluginHost()
    register(host)
    return host
