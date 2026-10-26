from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from launcher.timeutil import (DEVICE, ZONES, SPECIAL, ZoneBook, convert_to_device, filter_entries,
                               relative_text, resolve_zone, zone_issue)

NY = ZoneInfo("America/New_York")
MYT = timezone(timedelta(hours=8))


def test_gap_and_ambiguous():
    assert zone_issue(datetime(2026, 3, 8, 2, 30), NY) == "gap"
    assert zone_issue(datetime(2026, 11, 1, 1, 30), NY) == "ambiguous"
    assert zone_issue(datetime(2026, 7, 1, 12, 0), NY) is None


def test_convert():
    assert convert_to_device(datetime(2026, 7, 1, 9, 0), NY, MYT) == datetime(2026, 7, 1, 21, 0)
    assert convert_to_device(datetime(2026, 12, 1, 9, 0), NY, MYT) == datetime(2026, 12, 1, 22, 0)


def test_zonebook_without_tzdata():
    def fail(key):
        raise KeyError(key)
    zb = ZoneBook(fail)
    assert zb.incomplete
    assert "Asia/Kuala_Lumpur" in zb.names and "America/New_York" not in zb.names
    assert zb.get("Asia/Tokyo").utcoffset(None) == timedelta(hours=9)


def test_zonebook_full_and_offsets_by_date():
    zb = ZoneBook()
    if zb.incomplete:
        return
    rows = dict((k, l) for l, k in zb.entries(datetime(2026, 7, 1)))
    rows2 = dict((k, l) for l, k in zb.entries(datetime(2026, 12, 1)))
    assert rows["America/New_York"] != rows2["America/New_York"]
    assert len(zb.entries(datetime(2026, 7, 1))) == len(ZONES) + len(SPECIAL)


def test_resolve_and_filter():
    names = {DEVICE: "Device time (default)", "UTC": "UTC", "America/New_York": "Eastern Time · New York"}
    assert resolve_zone("ET", names) == "America/New_York"
    assert resolve_zone("new york", names) == "America/New_York"
    assert resolve_zone("zzz", names) is None
    assert resolve_zone("", names) is None
    entries = [("Eastern Time · New York (UTC-05:00)", "America/New_York"), ("UTC", "UTC")]
    assert filter_entries(entries, "york") == [entries[0][0]]
    assert len(filter_entries(entries, "nomatch")) == 2


def test_relative():
    now = datetime(2026, 1, 1, 12, 0)
    assert relative_text(now + timedelta(days=2, hours=3, minutes=5), now) == "in 2d 3h 5m"
    assert relative_text(now - timedelta(minutes=1), now) == "in the past"
