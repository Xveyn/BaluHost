__all__ = ["__version__"]

from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("baluhost-backend")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
