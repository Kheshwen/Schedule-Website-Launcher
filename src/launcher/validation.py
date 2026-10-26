"""Input validation and quoting.

Everything that ends up inside a PowerShell script or a Task Scheduler action passes through here:

* URLs are parsed and rebuilt (normalize_url), not just checked, so what is scheduled is always a
  clean http(s) address with nothing in it that could break out of a quoted string.
* Text placed in a PowerShell script is always wrapped by ps_quote.
* Task names are checked against one strict pattern before they are used or deleted.
"""
import ipaddress
import re
import secrets
from datetime import datetime
from urllib.parse import quote, urlsplit, urlunsplit

TASK_PREFIX = "AutoWeb_"
MAX_URL_LENGTH = 2048

# Letters, digits, "_" and "-" only. fullmatch is used, so a trailing newline can't sneak through.
TASK_NAME_RE = re.compile(r"AutoWeb_[A-Za-z0-9_-]{1,150}")

_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
# Characters kept as they are in the path, query and fragment. Everything else (quotes, spaces,
# backticks, backslashes, <, >, ^, |, {, } and non-ASCII) is percent-encoded.
_KEEP = "-._~:/?#[]@!$&()*+,;=%"
# PowerShell treats all of these as a single quote.
_PS_QUOTES = "'‘’‚‛"


class InvalidURL(ValueError):
    """The text isn't a link this app is willing to schedule. The message is safe to show the user."""


def _has_control_chars(text: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in text)


def ps_quote(text: str) -> str:
    """Turns text into a PowerShell single-quoted string literal.

    Inside one, the only special characters are the quote characters, which are escaped by doubling.
    Control characters (including newlines) are refused outright.
    """
    if _has_control_chars(text):
        raise ValueError("Control characters are not allowed.")
    return "'" + "".join(c * 2 if c in _PS_QUOTES else c for c in text) + "'"


def _clean_host(host: str) -> str:
    if ":" in host:  # IPv6 address
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise InvalidURL("That web address isn't valid.") from None
        if ip.version != 6:
            raise InvalidURL("That web address isn't valid.")
        return f"[{ip.compressed}]"
    try:
        ascii_host = host.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        raise InvalidURL("That web address isn't valid.") from None
    labels = ascii_host.split(".")
    if not ascii_host or len(ascii_host) > 253 or not all(_LABEL_RE.fullmatch(label) for label in labels):
        raise InvalidURL("That web address isn't valid.")
    return ascii_host


def _clean_part(text: str) -> str:
    return quote(_BAD_PERCENT.sub("%25", text), safe=_KEEP)


def normalize_url(raw: str) -> str:
    """Returns a safe http(s) URL built from what the user typed, or raises InvalidURL.

    Accepts "youtube.com" (https:// is added). Refuses other schemes (file:, javascript:, ...),
    addresses with a user name or password, bad host names and ports, control characters, and
    anything over 2048 characters. Unsafe characters in the path and query are percent-encoded.
    Running it on its own output changes nothing.
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidURL("URL cannot be empty.")
    if len(text) > MAX_URL_LENGTH:
        raise InvalidURL("That link is too long.")
    if _has_control_chars(text):
        raise InvalidURL("That link contains characters that aren't allowed.")
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise InvalidURL("That web address or port number isn't valid.") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidURL("Only http and https links are allowed.")
    if "@" in parts.netloc:
        raise InvalidURL("Links with a user name or password aren't allowed.")
    if not parts.hostname:
        raise InvalidURL("That link has no website address.")
    netloc = _clean_host(parts.hostname) + (f":{port}" if port is not None else "")
    url = urlunsplit((
        parts.scheme.lower(), netloc,
        _clean_part(parts.path), _clean_part(parts.query), _clean_part(parts.fragment),
    ))
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURL("That link is too long.")
    return url


def redact_url(url: str) -> str:
    """Just the host name, for the log."""
    try:
        return urlsplit(url).hostname or "?"
    except ValueError:
        return "?"


def is_managed_task_name(name: str) -> bool:
    """True only for names this app could have created."""
    return bool(TASK_NAME_RE.fullmatch(name or ""))


def make_task_name(host: str, now: datetime, shutdown: bool = False) -> str:
    """AutoWeb_<host>_<HHMMSS>_<4 random hex>. The random part stops two tasks made in the same
    second from overwriting each other."""
    stem = "SHUTDOWN" if shutdown else (re.sub(r"[^A-Za-z0-9_-]", "_", host or "")[:60] or "WebLaunch")
    return f"{TASK_PREFIX}{stem}_{now:%H%M%S}_{secrets.token_hex(2)}"
