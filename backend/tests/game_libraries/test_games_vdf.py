"""Tests for the minimal VDF (Valve KeyValues) parser."""

from app.services.game_libraries import vdf

SAMPLE = '''
"libraryfolders"
{
    "0"
    {
        "path"          "/home/sven/.local/share/Steam"
        "apps"
        {
            "228980"        "462054788"
            "1070560"       "222208995"
        }
    }
    "1"
    {
        "path"          "/mnt/cache-vcl/SteamLibrary"
        "apps"
        {
            "400"           "4347052354"
        }
    }
}
'''


def test_parse_nested_libraryfolders():
    data = vdf.parse(SAMPLE)
    libs = data["libraryfolders"]
    assert libs["0"]["path"] == "/home/sven/.local/share/Steam"
    assert libs["0"]["apps"]["228980"] == "462054788"
    assert libs["1"]["path"] == "/mnt/cache-vcl/SteamLibrary"
    assert libs["1"]["apps"]["400"] == "4347052354"


def test_parse_appmanifest_shape():
    acf = '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n    "SizeOnDisk" "35000000000"\n}'
    data = vdf.parse(acf)
    assert data["AppState"]["name"] == "Counter-Strike 2"
    assert data["AppState"]["SizeOnDisk"] == "35000000000"


def test_parse_empty_and_malformed():
    assert vdf.parse("") == {}
    # A key with no value (trailing) must not raise.
    assert isinstance(vdf.parse('"orphan"'), dict)


def test_parse_unescapes_backslashes():
    data = vdf.parse('"path" "C:\\\\Program Files (x86)\\\\Steam"')
    assert data["path"] == "C:\\Program Files (x86)\\Steam"
