import random
import re
from datetime import datetime

import pytest

from launcher.validation import (InvalidURL, is_managed_task_name, make_task_name, normalize_url,
                                 ps_quote, redact_url)
from launcher.tasks import build_register_script

HOSTILE = [
    "file:///C:/Windows/System32/calc.exe", "javascript:alert(1)", "ftp://example.com",
    "https://user:pass@example.com", "https://example.com@evil.com", "https://exa mple.com",
    "https://example.com\nrm", "https://", "", "   ", "http://[::1", "https://example.com:99999",
    "https://-bad-.com", "https://" + "a" * 300 + ".com", "https://example.com/" + "a" * 3000,
    "https://1.2.3.4.5.6:x", "\x00",
]


@pytest.mark.parametrize("raw,expected", [
    ("youtube.com", "https://youtube.com"),
    ("  http://Example.COM/a b  ", "http://example.com/a%20b"),
    ("https://example.com/a?x=1&y=2#f", "https://example.com/a?x=1&y=2#f"),
    ("https://example.com:8080/", "https://example.com:8080/"),
    ("https://[::1]:80/x", "https://[::1]:80/x"),
])
def test_valid(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", HOSTILE)
def test_invalid(raw):
    with pytest.raises(InvalidURL):
        normalize_url(raw)


def test_idempotent_and_quotes_encoded():
    url = normalize_url("https://example.com/a'b\"c`d\\e<f>g|h^i{j}k\u2018l")
    assert normalize_url(url) == url
    assert not re.search(r"['\"`\\<>|^{}\u2018]", url)


def test_ps_quote():
    assert ps_quote("a'b") == "'a''b'"
    assert ps_quote("\u2018\u2019") == "'\u2018\u2018\u2019\u2019'"
    for bad in ("a\nb", "a\x00b", "a\rb"):
        with pytest.raises(ValueError):
            ps_quote(bad)


def test_task_names():
    assert is_managed_task_name("AutoWeb_example.com_x") is False  # dot not allowed
    assert is_managed_task_name("AutoWeb_example_com_120000_ab12")
    assert not is_managed_task_name("AutoWeb_x\n")
    assert not is_managed_task_name("AutoWeb_x'; Remove-Item *")
    assert not is_managed_task_name("Other_x")
    assert not is_managed_task_name("")


def test_make_task_name_hostile_hosts():
    now = datetime(2026, 1, 1, 12, 0, 0)
    for host in ["a'b", "x;y", "evil\n", "é.com", "", None, "a" * 500]:
        assert is_managed_task_name(make_task_name(host, now))
    assert is_managed_task_name(make_task_name("", now, shutdown=True))
    assert make_task_name("x", now) != make_task_name("x", now)


def test_redact():
    assert redact_url("https://example.com/path?token=secret") == "example.com"


def _skeleton(script):
    """Remove single-quoted literals (a doubled quote char is an escape)."""
    q = "'\u2018\u2019\u201a\u201b"
    out, i, inside = [], 0, False
    while i < len(script):
        c = script[i]
        if inside:
            if c in q:
                if i + 1 < len(script) and script[i + 1] in q:
                    i += 2
                    continue
                inside = False
        else:
            if c in q:
                inside = True
            else:
                out.append(c)
        i += 1
    assert not inside, "unterminated literal"
    return "".join(out)


def test_fuzz_script_structure_unchanged():
    rng = random.Random(1234)
    alphabet = "'\"`$;(){}|&<>\\ \u2018\u2019\u201a\u201b%abc./:?#=-_é\n\r\x00"
    dt = datetime(2030, 1, 1, 9, 30)
    exe = r"C:\Windows\explorer.exe"
    base = _skeleton(build_register_script("AutoWeb_a_b", exe, "https://example.com", dt, True))
    for _ in range(3000):
        raw = "https://example.com/" + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40)))
        try:
            url = normalize_url(raw)
        except InvalidURL:
            continue
        script = build_register_script("AutoWeb_a_b", exe, url, dt, True)
        assert _skeleton(script) == base
