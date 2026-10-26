"""Talking to Windows Task Scheduler through PowerShell.

All scripts are built from validated values wrapped by ps_quote. Programs are started by absolute
path, with a time limit, and the kind of a task (website / shutdown) is decided by the program the
task runs, never by its name.
"""
import csv
import io
import logging
import ntpath
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .paths import windows_path
from .validation import (InvalidURL, is_managed_task_name, normalize_url, ps_quote, redact_url)

log = logging.getLogger("launcher.tasks")

ALLOWED_EXES = {"explorer.exe", "shutdown.exe"}
SHUTDOWN_ARGS = "/s /t 60"
CREATE_NO_WINDOW = 0x08000000

# Locale independent output: ISO dates, invariant culture.
PS_LIST = (
    "Get-ScheduledTask | Where-Object { $_.TaskName -like 'AutoWeb_*' } | ForEach-Object { "
    "$i = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue; "
    "$a = $_.Actions | Select-Object -First 1; "
    "$n = ''; if ($i -and $i.NextRunTime -and $i.NextRunTime.Year -gt 2000) "
    "{ $n = $i.NextRunTime.ToString('yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture) }; "
    "[pscustomobject]@{ Name = $_.TaskName; Exec = $a.Execute; Args = $a.Arguments; Next = $n } } "
    "| ConvertTo-Csv -NoTypeInformation"
)


def launch_exe() -> str:
    return windows_path("explorer.exe")


def shutdown_exe() -> str:
    return windows_path("System32", "shutdown.exe")


@dataclass(frozen=True)
class Task:
    name: str
    exe: str
    arg: str
    next_run: datetime | None

    @property
    def kind(self) -> str:
        base = ntpath.basename((self.exe or "").strip().strip('"')).lower()
        if base == "shutdown.exe":
            return "shutdown"
        if base == "explorer.exe":
            return "launch"
        return "other"

    @property
    def url(self) -> str:
        return (self.arg or "").strip().strip('"') if self.kind == "launch" else ""

    @property
    def status(self) -> str:
        return "Pending" if self.next_run else "Done"

    @property
    def label(self) -> str:
        if self.kind == "shutdown":
            return "Shutdown PC"
        return self.url or self.name


def parse_task_list(csv_text: str) -> list[Task]:
    tasks = []
    for row in csv.DictReader(io.StringIO(csv_text or "")):
        name = (row.get("Name") or "").strip()
        if not is_managed_task_name(name):
            continue
        nxt = None
        text = (row.get("Next") or "").strip()
        if text:
            try:
                nxt = datetime.strptime(text, "%Y-%m-%d %H:%M")
            except ValueError:
                nxt = None
        tasks.append(Task(name, row.get("Exec") or "", row.get("Args") or "", nxt))
    return tasks


def build_register_script(name: str, exe: str, arg: str, dt: datetime, catch_up: bool) -> str:
    if not is_managed_task_name(name):
        raise ValueError("Invalid task name.")
    if ntpath.basename(exe).lower() not in ALLOWED_EXES:
        raise ValueError("Program not allowed.")
    settings = "New-ScheduledTaskSettingsSet"
    if catch_up:
        settings += " -WakeToRun -StartWhenAvailable"
    return (
        "$ErrorActionPreference = 'Stop'; "
        f"$a = New-ScheduledTaskAction -Execute {ps_quote(exe)} -Argument {ps_quote(arg)}; "
        f"$t = New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact({ps_quote(dt.strftime('%Y-%m-%dT%H:%M:00'))}, "
        "'yyyy-MM-ddTHH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)); "
        f"$s = {settings}; "
        f"Register-ScheduledTask -TaskName {ps_quote(name)} -Action $a -Trigger $t -Settings $s -Force | Out-Null"
    )


def build_unregister_script(names: list[str]) -> str:
    for n in names:
        if not is_managed_task_name(n):
            raise ValueError("Invalid task name.")
    stmts = [
        f"Unregister-ScheduledTask -TaskName {ps_quote(n)} -Confirm:$false -ErrorAction Stop" for n in names
    ]
    return "$ErrorActionPreference = 'Stop'; " + "; ".join(stmts)


def powershell_exe() -> str:
    path = windows_path("System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path


def run_powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    flags = CREATE_NO_WINDOW if hasattr(subprocess, "STARTUPINFO") else 0
    return subprocess.run(
        [powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=flags,
    )


@dataclass(frozen=True)
class TaskResult:
    ok: bool
    error: str = ""


Runner = Callable[..., "subprocess.CompletedProcess"]


class TaskService:
    def __init__(self, runner: Runner = run_powershell):
        self._run = runner

    def _exec(self, script: str, what: str) -> TaskResult:
        try:
            r = self._run(script)
        except subprocess.TimeoutExpired:
            log.error("%s: timed out", what)
            return TaskResult(False, "Windows took too long to respond.")
        except OSError as exc:
            log.error("%s: could not start PowerShell: %s", what, exc)
            return TaskResult(False, "Could not start PowerShell.")
        if r.returncode != 0:
            log.error("%s failed: %s", what, (r.stderr or "").strip()[:500])
            return TaskResult(False, (r.stderr or "").strip()[:300] or "Windows reported an error.")
        return TaskResult(True)

    def list_tasks(self) -> tuple[list[Task], TaskResult]:
        try:
            r = self._run(PS_LIST)
        except subprocess.TimeoutExpired:
            log.error("list: timed out")
            return [], TaskResult(False, "Windows took too long to respond.")
        except OSError as exc:
            log.error("list: could not start PowerShell: %s", exc)
            return [], TaskResult(False, "Could not start PowerShell.")
        if r.returncode != 0:
            log.error("list failed: %s", (r.stderr or "").strip()[:500])
            return [], TaskResult(False, "Could not read the task list.")
        return parse_task_list(r.stdout), TaskResult(True)

    def register_launch(self, name: str, url: str, dt: datetime) -> TaskResult:
        try:
            url = normalize_url(url)
            script = build_register_script(name, launch_exe(), url, dt, catch_up=True)
        except (InvalidURL, ValueError) as exc:
            return TaskResult(False, str(exc))
        res = self._exec(script, "register launch")
        if res.ok:
            log.info("Scheduled launch of %s at %s", redact_url(url), dt.isoformat(timespec="minutes"))
        return res

    def register_shutdown(self, name: str, dt: datetime) -> TaskResult:
        try:
            script = build_register_script(name, shutdown_exe(), SHUTDOWN_ARGS, dt, catch_up=False)
        except ValueError as exc:
            return TaskResult(False, str(exc))
        res = self._exec(script, "register shutdown")
        if res.ok:
            log.info("Scheduled shutdown at %s", dt.isoformat(timespec="minutes"))
        return res

    def delete(self, names: list[str]) -> TaskResult:
        if not names:
            return TaskResult(True)
        try:
            script = build_unregister_script(names)
        except ValueError as exc:
            return TaskResult(False, str(exc))
        res = self._exec(script, "delete")
        if res.ok:
            log.info("Deleted %d task(s)", len(names))
        return res


def abort_shutdown(runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run) -> bool:
    try:
        r = runner([shutdown_exe(), "/a"], capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
