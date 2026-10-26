"""Where things live on disk."""
import ntpath
import os
import sys

APP_DIR_NAME = "WebsiteLauncher"


def app_data_dir() -> str:
    """Folder for settings and the log file (%APPDATA%\\WebsiteLauncher)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME)


def resource_path(name: str) -> str:
    """Path to a bundled file such as icon.ico, both from source and from the PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


def windows_path(*parts: str) -> str:
    """Absolute path inside the Windows folder, e.g. windows_path("System32", "shutdown.exe").

    Used instead of bare program names so a look-alike .exe in the app's folder or on PATH can't be run.
    """
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return ntpath.join(root, *parts)
