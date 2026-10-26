"""Time zone list, name matching and conversion. No window code in here."""
import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Callable
from zoneinfo import ZoneInfo

DEVICE = "device"
SPECIAL = {DEVICE: "Device time (default)", "UTC": "UTC"}

# One entry per region people actually use: (IANA name, label, fallback UTC offset in hours).
ZONES = [
    ("Pacific/Honolulu", "Hawaii · Honolulu", -10),
    ("America/Anchorage", "Alaska · Anchorage", -9),
    ("America/Los_Angeles", "Pacific Time · Los Angeles", -8),
    ("America/Denver", "Mountain Time · Denver", -7),
    ("America/Chicago", "Central Time · Chicago", -6),
    ("America/New_York", "Eastern Time · New York", -5),
    ("America/Halifax", "Atlantic Time · Halifax", -4),
    ("America/St_Johns", "Newfoundland · St. John's", -3.5),
    ("America/Sao_Paulo", "Brazil · Sao Paulo", -3),
    ("Europe/London", "UK · London", 0),
    ("Europe/Berlin", "Central Europe · Berlin", 1),
    ("Europe/Athens", "Eastern Europe · Athens", 2),
    ("Africa/Cairo", "Egypt · Cairo", 2),
    ("Africa/Johannesburg", "South Africa · Johannesburg", 2),
    ("Europe/Moscow", "Russia · Moscow", 3),
    ("Europe/Istanbul", "Turkey · Istanbul", 3),
    ("Asia/Riyadh", "Saudi Arabia · Riyadh", 3),
    ("Africa/Nairobi", "East Africa · Nairobi", 3),
    ("Asia/Tehran", "Iran · Tehran", 3.5),
    ("Asia/Dubai", "UAE · Dubai", 4),
    ("Asia/Karachi", "Pakistan · Karachi", 5),
    ("Asia/Kolkata", "India · Kolkata", 5.5),
    ("Asia/Kathmandu", "Nepal · Kathmandu", 5.75),
    ("Asia/Dhaka", "Bangladesh · Dhaka", 6),
    ("Asia/Bangkok", "Thailand / Vietnam · Bangkok", 7),
    ("Asia/Jakarta", "Indonesia · Jakarta", 7),
    ("Asia/Kuala_Lumpur", "Malaysia / Singapore · Kuala Lumpur", 8),
    ("Asia/Shanghai", "China · Shanghai", 8),
    ("Asia/Hong_Kong", "Hong Kong", 8),
    ("Asia/Manila", "Philippines · Manila", 8),
    ("Australia/Perth", "Western Australia · Perth", 8),
    ("Asia/Tokyo", "Japan · Tokyo", 9),
    ("Asia/Seoul", "Korea · Seoul", 9),
    ("Australia/Adelaide", "Australia · Adelaide", 9.5),
    ("Australia/Sydney", "Australia · Sydney / Melbourne", 10),
    ("Pacific/Auckland", "New Zealand · Auckland", 12),
]

# Regions without daylight saving: safe to fall back to a fixed offset if the time zone data is missing.
# Other regions are left out in that case, because a fixed offset would be an hour off for part of the year.
NO_DST = {
    "Pacific/Honolulu", "America/Sao_Paulo", "Europe/Moscow", "Europe/Istanbul", "Africa/Johannesburg",
    "Asia/Riyadh", "Africa/Nairobi", "Asia/Tehran", "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata",
    "Asia/Kathmandu", "Asia/Dhaka", "Asia/Bangkok", "Asia/Jakarta", "Asia/Kuala_Lumpur", "Asia/Shanghai",
    "Asia/Hong_Kong", "Asia/Manila", "Australia/Perth", "Asia/Tokyo", "Asia/Seoul",
}

# Short names people type, e.g. "ET". They map to a real region, so daylight saving is handled automatically.
ALIASES = {
    "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York",
    "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago",
    "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver",
    "pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "akst": "America/Anchorage", "akdt": "America/Anchorage", "hst": "Pacific/Honolulu",
    "nst": "America/St_Johns", "ndt": "America/St_Johns", "brt": "America/Sao_Paulo",
    "gmt": "Europe/London", "bst": "Europe/London", "uk": "Europe/London",
    "cet": "Europe/Berlin", "cest": "Europe/Berlin", "eet": "Europe/Athens", "eest": "Europe/Athens",
    "sast": "Africa/Johannesburg", "msk": "Europe/Moscow", "eat": "Africa/Nairobi",
    "gst": "Asia/Dubai", "uae": "Asia/Dubai", "pkt": "Asia/Karachi", "ist": "Asia/Kolkata",
    "npt": "Asia/Kathmandu", "bdt": "Asia/Dhaka", "ict": "Asia/Bangkok", "wib": "Asia/Jakarta",
    "myt": "Asia/Kuala_Lumpur", "sgt": "Asia/Kuala_Lumpur", "hkt": "Asia/Hong_Kong",
    "pht": "Asia/Manila", "awst": "Australia/Perth", "jst": "Asia/Tokyo", "kst": "Asia/Seoul",
    "acst": "Australia/Adelaide", "acdt": "Australia/Adelaide",
    "aest": "Australia/Sydney", "aedt": "Australia/Sydney",
    "nzst": "Pacific/Auckland", "nzdt": "Pacific/Auckland",
}

OFFSET_TAIL = re.compile(r"\s*\(utc[^)]*\)\s*$", re.I)


def fmt_offset(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def zone_issue(dt: datetime, tz: tzinfo) -> str | None:
    """'gap' if the time doesn't exist (clocks jump forward), 'ambiguous' if it happens twice, else None."""
    first, second = dt.replace(tzinfo=tz, fold=0), dt.replace(tzinfo=tz, fold=1)
    if first.utcoffset() == second.utcoffset():
        return None
    round_trip = first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    return "gap" if round_trip != dt else "ambiguous"


def convert_to_device(dt: datetime, tz: tzinfo, device_tz: tzinfo | None = None) -> datetime:
    """Wall-clock time in `tz` -> wall-clock time on this device (or in `device_tz`, which tests use)."""
    return dt.replace(tzinfo=tz).astimezone(device_tz).replace(tzinfo=None)


def resolve_zone(text: str, names: dict[str, str]) -> str | None:
    """Turns what the user typed (a label, a part of it, or an abbreviation like ET) into one zone key, or None."""
    t = OFFSET_TAIL.sub("", text.strip()).strip().lower()
    if not t:
        return None
    for key, name in names.items():
        if t == name.lower():
            return key
    if ALIASES.get(t) in names:
        return ALIASES[t]
    hits = [
        k for k, n in names.items()
        if t in n.lower() or t in k.lower() or t in k.lower().replace("_", " ")
    ]
    return hits[0] if len(hits) == 1 else None


def relative_text(local: datetime, now: datetime) -> str:
    """'in 2d 3h 5m', or 'in the past'."""
    diff = int((local - now).total_seconds() // 60)
    if diff <= 0:
        return "in the past"
    d, rem = divmod(diff, 1440)
    h, m = divmod(rem, 60)
    parts = ([f"{d}d"] if d else []) + ([f"{h}h"] if h else []) + ([f"{m}m"] if m or not (d or h) else [])
    return "in " + " ".join(parts)


def filter_entries(entries: list[tuple[str, str]], text: str) -> list[str]:
    """Labels that match what is typed so far; all labels if nothing matches."""
    t = OFFSET_TAIL.sub("", text.strip()).strip().lower()
    shown = [label for label, key in entries if not t or t in label.lower() or ALIASES.get(t) == key]
    return shown or [label for label, _ in entries]


class ZoneBook:
    """The zones available on this machine.

    If the time zone database is missing, regions without daylight saving fall back to a fixed
    offset and the rest are left out (`incomplete` is then True) rather than being silently wrong.
    """

    def __init__(self, factory: Callable[[str], tzinfo] = ZoneInfo):
        self._factory = factory
        self._cache: dict[str, tzinfo] = {}
        self._names = {**SPECIAL}
        for key, name, _ in ZONES:
            try:
                self.get(key)
                self._names[key] = name
            except Exception:
                pass

    @property
    def names(self) -> dict[str, str]:
        return self._names

    @property
    def incomplete(self) -> bool:
        return len(self._names) < len(SPECIAL) + len(ZONES)

    def get(self, key: str) -> tzinfo | None:
        """The tzinfo for a key; None means 'device time'."""
        if key == DEVICE:
            return None
        if key not in self._cache:
            if key == "UTC":
                self._cache[key] = timezone.utc
            else:
                try:
                    self._cache[key] = self._factory(key)
                except Exception:
                    if key not in NO_DST:
                        raise
                    offset = next(h for k, _, h in ZONES if k == key)
                    self._cache[key] = timezone(timedelta(hours=offset))
        return self._cache[key]

    def entries(self, ref: datetime) -> list[tuple[str, str]]:
        """[(label, key)]: device time, UTC, then regions west to east with their offset on the date `ref`."""
        rows = []
        for key, name, _ in ZONES:
            if key in self._names:
                rows.append((ref.replace(tzinfo=self.get(key)).utcoffset(), name, key))
        rows.sort(key=lambda r: (r[0], r[1]))
        entries = [(SPECIAL[DEVICE], DEVICE), (SPECIAL["UTC"], "UTC")]
        entries += [(f"{name} (UTC{fmt_offset(off)})", key) for off, name, key in rows]
        return entries
