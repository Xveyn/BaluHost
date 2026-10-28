"""cache_path of SSDCacheConfigUpdate: absolute, no traversal."""
import pytest
from pydantic import ValidationError

from app.schemas.ssd_file_cache import SSDCacheConfigUpdate


@pytest.mark.parametrize(
    "path",
    ["/mnt/cache-vcl/filecache/md0", "C:\\data\\cache", "D:/data/cache", "\\\\srv\\share"],
)
def test_accepts_absolute_paths(path):
    assert SSDCacheConfigUpdate(cache_path=path).cache_path == path


def test_none_is_allowed():
    assert SSDCacheConfigUpdate().cache_path is None


@pytest.mark.parametrize(
    "path",
    ["", "relative/cache", "cache", "/mnt/../etc", "C:\\data\\..\\x", "/mnt/a\x00b", "../x"],
)
def test_rejects_relative_traversal_and_nul(path):
    with pytest.raises(ValidationError):
        SSDCacheConfigUpdate(cache_path=path)
