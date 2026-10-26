import json
import os

from launcher.settings import load_settings, save_settings


def test_roundtrip(tmp_path):
    p = str(tmp_path / "s" / "settings.json")
    data = {"geometry": "760x700+10+20", "zoomed": False, "dpi": 1, "sort_col": "Next",
            "sort_rev": True, "dim": False, "tz": "Asia/Tokyo", "theme": "dark"}
    assert save_settings(p, data)
    assert load_settings(p) == data
    assert not os.path.exists(p + ".tmp")


def test_garbage_and_missing(tmp_path):
    p = tmp_path / "s.json"
    assert load_settings(str(p)) == {}
    p.write_text("{not json")
    assert load_settings(str(p)) == {}
    p.write_text("[1,2]")
    assert load_settings(str(p)) == {}


def test_bad_types_and_unknown_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"geometry": "$(calc)", "zoomed": "yes", "dpi": True, "sort_col": "x",
                             "theme": "neon", "tz": "a b", "evil": 1, "dim": True}))
    assert load_settings(str(p)) == {"dim": True}


def test_oversized(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"dim": True, "pad": "x" * 70000}))
    assert load_settings(str(p)) == {}
