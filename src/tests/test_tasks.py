import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from launcher.tasks import (TaskService, build_register_script, build_unregister_script,
                            parse_task_list)

DT = datetime(2030, 5, 6, 7, 8)
EXPL = r"C:\Windows\explorer.exe"
SHUT = r"C:\Windows\System32\shutdown.exe"

CSV = (
    '"Name","Exec","Args","Next"\n'
    f'"AutoWeb_example_com_010101_ab12","{EXPL}","https://example.com","2030-05-06 07:08"\n'
    f'"AutoWeb_SHUTDOWN_example_com_010102_cd34","{EXPL}","https://SHUTDOWN.example.com",""\n'
    f'"AutoWeb_SHUTDOWN_010103_ef56","{SHUT}","/s /t 60","2030-05-06 09:00"\n'
    f'"AutoWeb_bad\'name","{EXPL}","x",""\n'
)


def fake(returncode=0, stdout="", stderr="", exc=None):
    calls = []

    def runner(script, *a, **k):
        calls.append(script)
        if exc:
            raise exc
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    runner.calls = calls
    return runner


def test_parse():
    tasks = parse_task_list(CSV)
    assert [t.kind for t in tasks] == ["launch", "launch", "shutdown"]
    assert tasks[1].url == "https://SHUTDOWN.example.com"  # spoofed name is still a website task
    assert tasks[0].next_run == DT.replace(hour=7, minute=8)
    assert tasks[1].status == "Done" and tasks[0].status == "Pending"
    assert tasks[2].label == "Shutdown PC"


def test_register_scripts():
    s = build_register_script("AutoWeb_a_b", EXPL, "https://example.com", DT, True)
    assert s.startswith("$ErrorActionPreference = 'Stop'; ")
    assert "-WakeToRun -StartWhenAvailable" in s
    assert "2030-05-06T07:08:00" in s
    s2 = build_register_script("AutoWeb_a_b", SHUT, "/s /t 60", DT, False)
    assert "-WakeToRun" not in s2
    with pytest.raises(ValueError):
        build_register_script("AutoWeb_a_b", r"C:\evil\calc.exe", "x", DT, True)
    with pytest.raises(ValueError):
        build_register_script("bad name", EXPL, "x", DT, True)


def test_unregister_rejects_bad_names():
    with pytest.raises(ValueError):
        build_unregister_script(["AutoWeb_ok", "x'; calc"])
    assert "AutoWeb_ok" in build_unregister_script(["AutoWeb_ok"])


def test_service_success_and_failure():
    r = fake()
    assert TaskService(r).register_launch("AutoWeb_a_b", "example.com", DT).ok
    assert "https://example.com" in r.calls[0]
    assert not TaskService(fake(returncode=1, stderr="boom")).register_shutdown("AutoWeb_a_b", DT).ok
    assert not TaskService(fake(exc=subprocess.TimeoutExpired("x", 1))).delete(["AutoWeb_a"]).ok
    assert not TaskService(fake(exc=FileNotFoundError())).delete(["AutoWeb_a"]).ok


def test_service_rejects_bad_input_without_running():
    r = fake()
    svc = TaskService(r)
    assert not svc.register_launch("AutoWeb_a_b", "file:///c:/x", DT).ok
    assert not svc.delete(["nope'"]).ok
    assert r.calls == []


def test_list():
    tasks, res = TaskService(fake(stdout=CSV)).list_tasks()
    assert res.ok and len(tasks) == 3
    _, res = TaskService(fake(returncode=1)).list_tasks()
    assert not res.ok


def test_logs_have_no_query_secrets(caplog):
    caplog.set_level("INFO", logger="launcher")
    TaskService(fake()).register_launch("AutoWeb_a_b", "https://example.com/p?token=SECRET", DT)
    assert "SECRET" not in caplog.text and "example.com" in caplog.text
