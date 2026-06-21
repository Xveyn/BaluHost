"""Avatar extension must come from the validated MIME, not the user filename (audit #3)."""
from app.api.routes.users import _AVATAR_EXT_BY_TYPE, _avatar_ext


def test_each_allowed_type_maps_to_safe_extension():
    assert _avatar_ext("image/jpeg") == ".jpg"
    assert _avatar_ext("image/png") == ".png"
    assert _avatar_ext("image/gif") == ".gif"
    assert _avatar_ext("image/webp") == ".webp"


def test_extensions_are_image_only():
    # No executable/markup extensions can ever be produced.
    assert set(_AVATAR_EXT_BY_TYPE.values()) == {".jpg", ".png", ".gif", ".webp"}
