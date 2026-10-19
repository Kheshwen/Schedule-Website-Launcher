import csv
import ctypes
import json
import os
import re
import subprocess
import sys
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import sv_ttk  # modern light/dark theme (optional: the app still works without it)
except Exception:
    sv_ttk = None

APP_VERSION = "3.2"
TASK_PREFIX = "AutoWeb_"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # stops console flashing in the .exe
DT_FMT = "%d/%m/%Y %H:%M"
AUTO_REFRESH_MS = 15000
SETTINGS_FILE = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "WebsiteLauncher",
    "settings.json",
)

# Filters by name inside PowerShell, so it only fetches our tasks (much faster)
PS_LIST = (
    "Get-ScheduledTask -TaskName 'AutoWeb_*' -ErrorAction SilentlyContinue | ForEach-Object { "
    "$i = $_ | Get-ScheduledTaskInfo; $n = ''; "
    "if ($i.NextRunTime -and $i.NextRunTime.Year -gt 2000) { $n = $i.NextRunTime.ToString('dd/MM/yyyy HH:mm') }; "
    "[pscustomobject]@{Name=$_.TaskName; Next=$n; Args=$_.Actions[0].Arguments} } | ConvertTo-Csv -NoTypeInformation"
)

# Laptop screen brightness (WMI)
WMI_GET = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness"
WMI_SET = (
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
    "ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName WmiSetBrightness -Arguments @{Timeout=1; Brightness=%d} }"
)

# ---------- Time zones ----------
DEVICE = "device"
SPECIAL = {DEVICE: "Device time (default)", "UTC": "UTC"}

# One entry per region people actually use: (IANA name, label, fallback UTC offset).
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


def fmt_offset(delta):
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def zone_issue(dt, tz):
    """Returns 'gap' if the time doesn't exist (clocks jump forward), 'ambiguous' if it happens twice, else None."""
    first, second = dt.replace(tzinfo=tz, fold=0), dt.replace(tzinfo=tz, fold=1)
    if first.utcoffset() == second.utcoffset():
        return None
    round_trip = first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    return "gap" if round_trip != dt else "ambiguous"


def resolve_zone(text, names):
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


# ---------- Theme ----------
PALETTE = {
    "light": {
        "bg": "#fafafa", "fg": "#1c1c1c", "field": "#ffffff", "accent": "#005fb8",
        "muted": "#707070", "sel_bg": "#005fb8", "sel_fg": "#ffffff"
    },
    "dark": {
        "bg": "#1c1c1c", "fg": "#fafafa", "field": "#2b2b2b", "accent": "#60cdff",
        "muted": "#9a9a9a", "sel_bg": "#57c8ff", "sel_fg": "#000000"
    },
}


def system_theme():
    """Reads the Windows light/dark setting."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "light"


def enable_dpi_awareness():
    """Stops Windows from blurring the window on high-resolution screens."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="ignore", creationflags=NOWIN)


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


class PlaceholderEntry(ttk.Entry):
    """Entry that shows grey hint text while it is empty and unfocused."""

    def __init__(self, master, placeholder, **kw):
        super().__init__(master, **kw)
        self.placeholder = placeholder
        self.showing = False
        self.muted = "#888888"
        self.bind("<FocusIn>", lambda e: self._hide(), add="+")
        self.bind("<FocusOut>", lambda e: self._show(), add="+")
        self._show()

    def value(self):
        return "" if self.showing else self.get()

    def clear(self):
        self._hide()
        self.delete(0, "end")
        try:
            focused = self.focus_get() is self
        except Exception:
            focused = False
        if not focused:
            self._show()

    def set_muted(self, color):
        self.muted = color
        if self.showing:
            self.configure(foreground=color)

    def _show(self):
        if not self.showing and not self.get():
            self.showing = True
            self.insert(0, self.placeholder)
            self.configure(foreground=self.muted)

    def _hide(self):
        if self.showing:
            self.delete(0, "end")
            self.showing = False
            self.configure(foreground="")


class PHYSICAL_MONITOR(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("handle", ctypes.c_void_p), ("desc", wintypes.WCHAR * 128)]


class Dimmer:
    """Lowers the real screen brightness: DDC/CI for external monitors, WMI for laptop screens."""

    def __init__(self):
        self.mode = None
        self.saved = None
        self.monitors = None

    def _dxva2(self):
        d = ctypes.windll.dxva2
        dw = wintypes.DWORD
        d.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, ctypes.POINTER(dw)]
        d.GetPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, dw, ctypes.POINTER(PHYSICAL_MONITOR)]
        d.GetMonitorBrightness.argtypes = [ctypes.c_void_p, ctypes.POINTER(dw), ctypes.POINTER(dw), ctypes.POINTER(dw)]
        d.SetMonitorBrightness.argtypes = [ctypes.c_void_p, dw]
        d.DestroyPhysicalMonitors.argtypes = [dw, ctypes.POINTER(PHYSICAL_MONITOR)]
        return d

    def dim(self):
        if self.mode:
            return
        if not self._dim_ddc():
            self._dim_wmi()

    def _dim_ddc(self):
        try:
            u, d = ctypes.windll.user32, self._dxva2()
            u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            u.MonitorFromWindow.restype = ctypes.c_void_p
            hmon = u.MonitorFromWindow(0, 1)  # primary monitor
            n = wintypes.DWORD()
            if not d.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value == 0:
                return False
            arr = (PHYSICAL_MONITOR * n.value)()
            if not d.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                return False
            saved = []
            for m in arr:
                lo, cur, hi = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                if d.GetMonitorBrightness(m.handle, ctypes.byref(lo), ctypes.byref(cur), ctypes.byref(hi)):
                    d.SetMonitorBrightness(m.handle, lo.value)
                    saved.append((m.handle, cur.value))
            if saved:
                self.mode, self.saved, self.monitors = "ddc", saved, arr
                return True
            d.DestroyPhysicalMonitors(n.value, arr)
        except Exception:
            pass
        return False

    def _dim_wmi(self):
        try:
            current = int(run(["powershell", "-NoProfile", "-Command", WMI_GET]).stdout.strip())
            if run(["powershell", "-NoProfile", "-Command", WMI_SET % 0]).returncode != 0:
                return False
            self.mode, self.saved = "wmi", current
            return True
        except Exception:
            return False

    def restore(self):
        mode, self.mode = self.mode, None
        try:
            if mode == "ddc":
                d = self._dxva2()
                for handle, level in self.saved:
                    d.SetMonitorBrightness(handle, level)
                d.DestroyPhysicalMonitors(len(self.monitors), self.monitors)
            elif mode == "wmi":
                run(["powershell", "-NoProfile", "-Command", WMI_SET % self.saved])
        except Exception:
            pass


NAV_KEYS = {
    "Return", "Tab", "Up", "Down", "Left", "Right", "Escape", "Home", "End",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"
}


class WebSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Schedule Website Launcher V{APP_VERSION}")
        self.settings = load_settings()
        self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.minsize(self.px(680), self.px(620))
        self.apply_saved_geometry()
        try:
            self.root.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            pass

        self.black = None
        self.dimmer = Dimmer()
        self.args = {}
        self.rows = []
        self.overdue_tries = {}
        self.status_job = None
        self.combos = []
        self._zones = {}
        self.tz_editing = False
        self.mode = "light"

        col = self.settings.get("sort_col")
        self.sort_col = col if col in ("Task", "Next", "Status") else "Next"
        self.sort_rev = bool(self.settings.get("sort_rev", False))

        pref = self.settings.get("theme")
        self.theme_pref = pref if pref in ("system", "light", "dark") else "system"

        self.zone_names = self.available_zone_names()
        saved_tz = self.settings.get("tz", DEVICE)
        self.tz_key = saved_tz if saved_tz in self.zone_names else DEVICE
        self.last_good_tz = self.tz_key

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.apply_theme()
        self.create_widgets()
        self.apply_theme()
        self.refresh_tz_widget(self.ref_datetime())
        self.update_form_info()
        self.refresh_task_list()
        self.root.after(AUTO_REFRESH_MS, self.auto_refresh)

    # ---------- Settings / window ----------
    def px(self, n):
        return int(n * self.scale)

    def apply_saved_geometry(self):
        self.root.geometry(f"{self.px(760)}x{self.px(700)}")
        m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", str(self.settings.get("geometry", "")))
        if m and self.settings.get("dpi") == 1:
            w, h = max(int(m.group(1)), self.px(680)), max(int(m.group(2)), self.px(620))
            x, y = int(m.group(3)), int(m.group(4))
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if -w + 100 < x < sw - 100 and 0 <= y < sh - 100:
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.root.geometry(f"{w}x{h}")
            if self.settings.get("zoomed"):
                self.root.state("zoomed")

    def on_close(self):
        self.close_black()
        try:
            state = self.root.state()
            if state != "normal":
                self.root.state("normal")
                self.root.update_idletasks()
            save_settings({
                "geometry": self.root.geometry(),
                "zoomed": state == "zoomed",
                "dpi": 1,
                "sort_col": self.sort_col,
                "sort_rev": self.sort_rev,
                "dim": self.dim_var.get(),
                "tz": self.last_good_tz,
                "theme": self.theme_pref,
            })
        except Exception:
            pass
        self.root.destroy()

    def set_status(self, message):
        self.status_var.set(message)
        if self.status_job:
            self.root.after_cancel(self.status_job)
        self.status_job = self.root.after(6000, lambda: self.status_var.set(""))

    # ---------- Theme ----------
    def apply_theme(self):
        self.mode = system_theme() if self.theme_pref == "system" else self.theme_pref
        if sv_ttk is None:
            self.mode = "light"
        pal = PALETTE[self.mode]
        if sv_ttk:
            try:
                sv_ttk.set_theme(self.mode)
            except Exception:
                pass
        try:
            ttk.Style().configure("Treeview", rowheight=self.px(28))
        except Exception:
            pass
        self.root.configure(bg=pal["bg"])
        if hasattr(self, "tree"):
            self.tree.tag_configure("pending", foreground=pal["accent"])
            self.tree.tag_configure("done", foreground=pal["muted"])
        if hasattr(self, "url_entry"):
            self.url_entry.set_muted(pal["muted"])
        if hasattr(self, "preview_label"):
            self.preview_label.configure(foreground=pal["accent"])
        self.style_combo_popups()
        self.set_titlebar(self.root)

    def on_theme_change(self, event=None):
        self.theme_pref = self.theme_var.get().lower()
        self.apply_theme()
        self.theme_combo.selection_clear()

    def set_titlebar(self, win):
        try:
            win.update_idletasks()
            user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            hwnd = user32.GetParent(win.winfo_id())
            value = ctypes.c_int(1 if self.mode == "dark" else 0)
            for attribute in (20, 19):
                if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def style_combo_popups(self):
        pal = PALETTE[self.mode]
        alive = []
        for cb in self.combos:
            try:
                if not cb.winfo_exists():
                    continue
                pop = self.root.tk.call("ttk::combobox::PopdownWindow", str(cb))
                self.root.tk.call(
                    f"{pop}.f.l", "configure",
                    "-background", pal["field"], "-foreground", pal["fg"],
                    "-selectbackground", pal["sel_bg"], "-selectforeground", pal["sel_fg"],
                    "-borderwidth", 0, "-highlightthickness", 0
                )
                alive.append(cb)
            except Exception:
                pass
        self.combos = alive

    def combo(self, parent, var, values, width, readonly=False):
        cb = ttk.Combobox(
            parent, textvariable=var, values=values, width=width,
            state="readonly" if readonly else "normal"
        )
        self.combos.append(cb)
        return cb

    # ---------- Time zone helpers ----------
    def zone(self, key):
        if key == DEVICE:
            return None
        if key not in self._zones:
            if key == "UTC":
                self._zones[key] = timezone.utc
            else:
                try:
                    self._zones[key] = ZoneInfo(key)
                except Exception:
                    off = next(h for k, _, h in ZONES if k == key)
                    self._zones[key] = timezone(timedelta(hours=off))
        return self._zones[key]

    def available_zone_names(self):
        names = dict(SPECIAL)
        for key, name, *_ in ZONES:
            try:
                self.zone(key)
                names[key] = name
            except Exception:
                pass
        return names

    def tz_entries(self, ref):
        rows = []
        for key, name, *_ in ZONES:
            if key in self.zone_names:
                rows.append((ref.replace(tzinfo=self.zone(key)).utcoffset(), name, key))
        rows.sort(key=lambda r: (r[0], r[1]))
        entries = [(SPECIAL[DEVICE], DEVICE), (SPECIAL["UTC"], "UTC")]
        entries += [(f"{name} (UTC{fmt_offset(off)})", key) for off, name, key in rows]
        return entries

    def entered_datetime(self):
        try:
            return datetime(
                int(self.year.get()), int(self.month.get()), int(self.day.get()),
                int(self.hour.get()), int(self.minute.get())
            )
        except ValueError:
            return None

    def ref_datetime(self):
        return self.entered_datetime() or datetime.now()

    def refresh_tz_widget(self, ref):
        entries = self.tz_entries(ref)
        self.tz_combo["values"] = [label for label, _ in entries]
        for label, key in entries:
            if key == self.tz_key:
                self.tz_var.set(label)
                break

    def preview_text(self, dt):
        key = self.tz_key
        if key is None:
            return "Choose a time zone from the list."
        if key == DEVICE:
            local, note = dt, ""
        else:
            tz = self.zone(key)
            issue = zone_issue(dt, tz)
            if issue == "gap":
                return "That time doesn't exist in this time zone because the clocks change. Pick another time."
            local = dt.replace(tzinfo=tz).astimezone().replace(tzinfo=None)
            note = "  (this time happens twice, the first one is used)" if issue == "ambiguous" else ""

        diff = int((local - datetime.now()).total_seconds() // 60)
        if diff <= 0:
            rel = "in the past"
        else:
            d, rem = divmod(diff, 1440)
            h, m = divmod(rem, 60)
            parts = ([f"{d}d"] if d else []) + ([f"{h}h"] if h else []) + ([f"{m}m"] if m or not (d or h) else [])
            rel = "in " + " ".join(parts)

        if key == DEVICE:
            return f"Scheduled {rel}"
        return f"Runs at {local:%a %d/%m/%Y %H:%M} your device time ({rel}){note}"

    def update_form_info(self, *_):
        dt = self.entered_datetime()
        if dt is None:
            self.day_var.set("")
            self.preview_var.set("")
            return
        self.day_var.set(dt.strftime("%a"))
        if not self.tz_editing:
            self.refresh_tz_widget(dt)
        self.preview_var.set(self.preview_text(dt))

    def tz_focus_in(self, event=None):
        self.tz_editing = True

    def tz_focus_out(self, event=None):
        self.tz_editing = False
        self.commit_tz(keep_previous=True)

    def tz_typing(self, event):
        if event.keysym in NAV_KEYS:
            return
        text = OFFSET_TAIL.sub("", self.tz_var.get().strip()).strip().lower()
        self.tz_key = resolve_zone(self.tz_var.get(), self.zone_names)
        entries = self.tz_entries(self.ref_datetime())
        shown = [label for label, key in entries if not text or text in label.lower() or ALIASES.get(text) == key]
        self.tz_combo["values"] = shown or [label for label, _ in entries]
        dt = self.entered_datetime()
        self.preview_var.set(self.preview_text(dt) if dt else "")

    def commit_tz(self, event=None, keep_previous=False):
        key = resolve_zone(self.tz_var.get(), self.zone_names)
        if key is None and keep_previous:
            key = self.last_good_tz
        if key is not None:
            self.tz_key = self.last_good_tz = key
        self.refresh_tz_widget(self.ref_datetime())
        dt = self.entered_datetime()
        self.preview_var.set(self.preview_text(dt) if dt else "")

    def on_tz_selected(self, event=None):
        self.commit_tz()
        self.tz_combo.selection_clear()

    def on_tz_return(self, event=None):
        if resolve_zone(self.tz_var.get(), self.zone_names) is None:
            messagebox.showwarning("Input Error", "That time zone isn't recognised. Pick one from the list.")
            return
        self.commit_tz()
        self.schedule_launch()

    def shift_time(self, **delta_kwargs):
        base = max(self.entered_datetime() or datetime.now(), datetime.now())
        target = base + timedelta(**delta_kwargs)
        self.day.set(f"{target.day:02d}")
        self.month.set(f"{target.month:02d}")
        self.year.set(str(target.year))
        self.hour.set(f"{target.hour:02d}")
        self.minute.set(f"{target.minute:02d}")

    # ---------- Layout ----------
    def create_widgets(self):
        accent = {"style": "Accent.TButton"} if sv_ttk else {}
        switch = {"style": "Switch.TCheckbutton"} if sv_ttk else {}

        bar = ttk.Frame(self.root)
        bar.pack(side="bottom", fill="x", padx=14, pady=(0, 8))
        self.status_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(side="left", fill="x", expand=True)
        if sv_ttk:
            self.theme_var = tk.StringVar(value=self.theme_pref.capitalize())
            self.theme_combo = self.combo(bar, self.theme_var, ["System", "Light", "Dark"], 8, readonly=True)
            self.theme_combo.pack(side="right")
            ttk.Label(bar, text="Theme:").pack(side="right", padx=(0, 6))
            self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)

        f = ttk.LabelFrame(self.root, text="Schedule", padding=12)
        f.pack(fill="x", padx=14, pady=(14, 10))

        ttk.Label(f, text="Website URL:").grid(row=0, column=0, sticky="w", pady=6)
        self.url_entry = PlaceholderEntry(f, "e.g. youtube.com", width=58)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="w", padx=6)

        d = datetime.now() + timedelta(minutes=5)
        self.day = tk.StringVar(value=f"{d.day:02d}")
        self.month = tk.StringVar(value=f"{d.month:02d}")
        self.year = tk.StringVar(value=str(d.year))
        self.hour = tk.StringVar(value=f"{d.hour:02d}")
        self.minute = tk.StringVar(value=f"{d.minute:02d}")
        self.day_var = tk.StringVar()
        self.preview_var = tk.StringVar()
        self.tz_var = tk.StringVar()

        ttk.Label(f, text="Date:").grid(row=1, column=0, sticky="w", pady=6)
        date_row = ttk.Frame(f)
        date_row.grid(row=1, column=1, columnspan=2, sticky="w", padx=6)
        self.combo(date_row, self.day, [f"{i:02d}" for i in range(1, 32)], 4).pack(side="left")
        ttk.Label(date_row, text="/").pack(side="left", padx=2)
        self.combo(date_row, self.month, [f"{i:02d}" for i in range(1, 13)], 4).pack(side="left")
        ttk.Label(date_row, text="/").pack(side="left", padx=2)
        self.combo(date_row, self.year, [str(d.year + i) for i in range(4)], 6).pack(side="left")
        ttk.Label(date_row, textvariable=self.day_var, width=5, anchor="w").pack(side="left", padx=(12, 0))

        ttk.Label(f, text="Time (24h):").grid(row=2, column=0, sticky="w", pady=6)
        time_row = ttk.Frame(f)
        time_row.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        self.combo(time_row, self.hour, [f"{i:02d}" for i in range(24)], 4).pack(side="left")
        ttk.Label(time_row, text=":").pack(side="left", padx=2)
        self.combo(time_row, self.minute, [f"{i:02d}" for i in range(60)], 4).pack(side="left")
        for label, kw in (("+15m", {"minutes": 15}), ("+1h", {"hours": 1}), ("+1d", {"days": 1})):
            ttk.Button(time_row, text=label, width=5, command=lambda k=kw: self.shift_time(**k)).pack(side="left", padx=(6, 0))

        ttk.Label(f, text="Time zone:").grid(row=3, column=0, sticky="w", pady=6)
        self.tz_combo = self.combo(f, self.tz_var, [], 46)
        self.tz_combo.grid(row=3, column=1, columnspan=2, sticky="w", padx=6)
        self.tz_combo.bind("<FocusIn>", self.tz_focus_in)
        self.tz_combo.bind("<FocusOut>", self.tz_focus_out)
        self.tz_combo.bind("<KeyRelease>", self.tz_typing)
        self.tz_combo.bind("<<ComboboxSelected>>", self.on_tz_selected)
        self.tz_combo.bind("<Return>", self.on_tz_return)

        self.preview_label = ttk.Label(f, textvariable=self.preview_var)
        self.preview_label.grid(row=4, column=1, columnspan=2, sticky="w", padx=6)

        for w in [self.url_entry] + [
            c for row in (date_row, time_row)
            for c in row.winfo_children() if isinstance(c, ttk.Combobox)
        ]:
            w.bind("<Return>", lambda e: self.schedule_launch())

        for var in (self.day, self.month, self.year, self.hour, self.minute):
            var.trace_add("write", self.update_form_info)

        btns = ttk.Frame(f)
        btns.grid(row=5, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text="Schedule Launch", command=self.schedule_launch, **accent).pack(side="left", padx=5)
        ttk.Button(btns, text="Schedule Shutdown", command=self.schedule_shutdown).pack(side="left", padx=5)
        ttk.Button(btns, text="Abort Shutdown Countdown", command=self.abort_shutdown).pack(side="left", padx=5)

        b = ttk.LabelFrame(self.root, text="Black Screen (audio keeps playing)", padding=12)
        b.pack(fill="x", padx=14, pady=(0, 10))
        self.black_btn = ttk.Button(b, text="Turn On Black Screen", command=self.toggle_black)
        self.black_btn.pack(side="left")
        self.dim_var = tk.BooleanVar(value=bool(self.settings.get("dim", True)))
        ttk.Checkbutton(b, text="Also lower brightness", variable=self.dim_var, **switch).pack(side="left", padx=14)
        ttk.Label(b, text="Esc or double-click to exit.").pack(side="left")

        lf = ttk.LabelFrame(
            self.root,
            text="Scheduled Tasks (click a heading to sort, double-click a task to edit)",
            padding=12
        )
        lf.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.tree = ttk.Treeview(
            lf, columns=("Task", "Day", "Next", "Status"),
            show="headings", height=8, selectmode="extended"
        )
        self.headings = {"Task": "Task / URL", "Day": "Day", "Next": "Next Run Time", "Status": "Status"}
        for col, w in (("Task", 280), ("Day", 60), ("Next", 140), ("Status", 80)):
            self.tree.heading(
                col, text=self.headings[col],
                command=lambda c=col: self.sort_by("Next" if c == "Day" else c)
            )
            self.tree.column(col, width=self.px(w), minwidth=self.px(50), stretch=(col == "Task"))
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

        # Context menu
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open URL Now", command=self.open_selected_now)
        self.menu.add_command(label="Copy URL", command=self.copy_selected_url)
        self.menu.add_separator()
        self.menu.add_command(label="Edit", command=self.edit_selected)
        self.menu.add_command(label="Delete", command=self.delete_selected)
        self.tree.bind("<Button-3>", self.show_context_menu)

        bf = ttk.Frame(self.root)
        bf.pack(fill="x", padx=14, pady=(0, 10))
        ttk.Button(bf, text="Refresh", command=self.refresh_task_list).pack(side="left", padx=5)
        ttk.Button(bf, text="Clear Past Tasks", command=self.clear_past).pack(side="left", padx=5)
        ttk.Button(bf, text="Edit Selected", command=self.edit_selected).pack(side="left", padx=5)
        ttk.Button(bf, text="Delete Selected", command=self.delete_selected).pack(side="right", padx=5)

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def open_selected_now(self):
        for name in self.tree.selection():
            url = self.args.get(name, "").strip().strip('"')
            if url and "SHUTDOWN" not in name:
                os.startfile(url)

    def copy_selected_url(self):
        sel = self.tree.selection()
        if sel:
            url = self.args.get(sel[0], "").strip().strip('"')
            if url:
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.set_status("Copied URL to clipboard.")

    # ---------- Inputs ----------
    def get_datetime(self):
        dt = self.entered_datetime()
        if dt is None:
            messagebox.showwarning("Input Error", "That date or time isn't valid. Please use numbers only and check the values.")
            return None
        key = self.tz_key
        if key is None:
            messagebox.showwarning("Input Error", "Choose a time zone from the list.")
            return None
        if key != DEVICE:
            tz = self.zone(key)
            issue = zone_issue(dt, tz)
            if issue == "gap":
                messagebox.showwarning(
                    "Input Error",
                    "That time doesn't exist in this time zone because the clocks "
                    "change that day. Please pick another time."
                )
                return None
            if issue == "ambiguous" and not messagebox.askokcancel(
                "Time happens twice",
                "The clocks go back in that time zone, so this time happens twice. "
                "The first one will be used. Continue?"
            ):
                return None
            dt = dt.replace(tzinfo=tz).astimezone().replace(tzinfo=None)
        if dt <= datetime.now():
            messagebox.showwarning("Input Error", "The scheduled time must be in the future.")
            return None
        return dt

    def register_task(self, name, exe, arg, dt):
        ps_script = (
            f"$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '{arg.replace(chr(39), chr(39)*2)}'; "
            f"$t = New-ScheduledTaskTrigger -Once -At '{dt:%Y-%m-%dT%H:%M:00}'; "
            f"$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable; "
            f"Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger $t -Settings $s -Force | Out-Null"
        )
        result = run(["powershell", "-NoProfile", "-Command", ps_script])
        if result.returncode == 0:
            self.refresh_task_list()
            return True
        messagebox.showerror("System Error", f"Could not schedule task.\n\n{result.stderr}")
        return False

    # ---------- Schedule ----------
    def schedule_launch(self):
        url = self.url_entry.value().strip()
        if not url:
            messagebox.showwarning("Input Error", "URL cannot be empty.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        dt = self.get_datetime()
        if not dt:
            return

        domain = re.sub(r"[^A-Za-z0-9_-]", "_", urlparse(url).netloc) or "WebLaunch"
        name = f"{TASK_PREFIX}{domain}_{datetime.now():%H%M%S}"
        if self.register_task(name, "explorer.exe", f'"{url}"', dt):
            self.set_status(f"Scheduled {url} for {dt:%a %d/%m/%Y %H:%M} (your device time).")
            self.url_entry.clear()

    def schedule_shutdown(self):
        dt = self.get_datetime()
        if not dt:
            return
        name = f"{TASK_PREFIX}SHUTDOWN_{datetime.now():%H%M%S}"
        if self.register_task(name, "shutdown.exe", "/s /t 60", dt):
            self.set_status(f"PC will start shutting down at {dt:%a %d/%m/%Y %H:%M} (60 sec countdown).")

    def abort_shutdown(self):
        result = run(["shutdown", "/a"])
        if result.returncode == 0:
            self.set_status("Shutdown countdown cancelled.")
        else:
            self.set_status("No shutdown countdown is running right now.")

    # ---------- Task list ----------
    def refresh_task_list(self):
        self.args, self.rows = {}, []
        try:
            result = run(["powershell", "-NoProfile", "-Command", PS_LIST])
            if result.returncode == 0 and result.stdout.strip():
                for row in csv.DictReader(StringIO(result.stdout)):
                    name, nxt = row.get("Name", ""), row.get("Next", "")
                    args = (row.get("Args") or "").strip()
                    self.args[name] = args
                    shown = "Shutdown PC" if "SHUTDOWN" in name else (args.strip('"') or name)
                    self.rows.append((name, shown, nxt, "Pending" if nxt else "Done"))
        except Exception:
            pass
        self.render_tasks()

    def auto_refresh(self):
        now = datetime.now()
        due = []
        for name, shown, nxt, status in self.rows:
            if status == "Pending":
                try:
                    if datetime.strptime(nxt, DT_FMT) <= now:
                        due.append((name, nxt))
                except ValueError:
                    pass
        fresh = [k for k in due if self.overdue_tries.get(k, 0) < 4]
        if fresh:
            for k in fresh:
                self.overdue_tries[k] = self.overdue_tries.get(k, 0) + 1
            self.refresh_task_list()
        self.root.after(AUTO_REFRESH_MS, self.auto_refresh)

    def sort_key(self, row):
        name, shown, nxt, status = row
        if self.sort_col == "Next":
            try:
                return datetime.strptime(nxt, DT_FMT)
            except ValueError:
                return datetime.max
        return (shown if self.sort_col == "Task" else status).lower()

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if col == self.sort_col else False
        self.sort_col = col
        self.render_tasks()

    def render_tasks(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for name, shown, nxt, status in sorted(self.rows, key=self.sort_key, reverse=self.sort_rev):
            try:
                day = datetime.strptime(nxt, DT_FMT).strftime("%a")
            except ValueError:
                day = "-"
            self.tree.insert(
                "", "end", iid=name, values=(shown, day, nxt or "-", status),
                tags=("pending" if status == "Pending" else "done",)
            )
        keep = [i for i in selected if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)
        for col, text in self.headings.items():
            arrow = (" ▼" if self.sort_rev else " ▲") if col == self.sort_col else ""
            self.tree.heading(col, text=text + arrow)

    def on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self.edit_selected()

    def delete_tasks(self, names):
        quoted = ",".join(f"'{n}'" for n in names)
        ps_cmd = f"Unregister-ScheduledTask -TaskName {quoted} -Confirm:$false"
        result = run(["powershell", "-NoProfile", "-Command", ps_cmd])
        self.refresh_task_list()
        if result.returncode != 0:
            messagebox.showerror("Error", f"Failed to delete tasks:\n{result.stderr}")
        else:
            self.set_status(f"Deleted {len(names)} task(s).")

    def delete_selected(self):
        names = list(self.tree.selection())
        if not names:
            self.set_status("Select a task from the list first.")
            return
        if messagebox.askyesno("Confirm Deletion", f"Delete {len(names)} selected task(s)?"):
            self.delete_tasks(names)

    def clear_past(self):
        names = [i for i in self.tree.get_children() if self.tree.item(i, "values")[3] == "Done"]
        if not names:
            self.set_status("There are no past tasks to clear.")
            return
        if messagebox.askyesno("Clear Past Tasks", f"Delete {len(names)} finished task(s)?"):
            self.delete_tasks(names)

    # ---------- Edit ----------
    def edit_selected(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            self.set_status("Select one task to edit.")
            return
        name = sel[0]
        is_shutdown = "SHUTDOWN" in name
        values = self.tree.item(name, "values")
        try:
            d = datetime.strptime(values[2], DT_FMT)
        except ValueError:
            d = datetime.now() + timedelta(minutes=5)

        win = tk.Toplevel(self.root)
        win.title("Edit Task")
        win.configure(bg=PALETTE[self.mode]["bg"])
        win.resizable(False, False)
        win.transient(self.root)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        outer = ttk.Frame(win, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=values[0]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        url_var = tk.StringVar(value=self.args.get(name, "").strip().strip('"'))
        if not is_shutdown:
            ttk.Label(outer, text="Website URL:").grid(row=1, column=0, sticky="w", pady=6)
            ttk.Entry(outer, textvariable=url_var, width=45).grid(row=1, column=1, padx=10)

        v = {
            k: tk.StringVar(value=val) for k, val in (
                ("d", f"{d.day:02d}"), ("m", f"{d.month:02d}"), ("y", str(d.year)),
                ("h", f"{d.hour:02d}"), ("min", f"{d.minute:02d}")
            )
        }
        day_var = tk.StringVar(value=d.strftime("%a"))

        def update_day(*_):
            try:
                day_var.set(datetime(int(v["y"].get()), int(v["m"].get()), int(v["d"].get())).strftime("%a"))
            except ValueError:
                day_var.set("")

        for key in ("d", "m", "y"):
            v[key].trace_add("write", update_day)

        ttk.Label(outer, text="Date:").grid(row=2, column=0, sticky="w", pady=6)
        dr = ttk.Frame(outer)
        dr.grid(row=2, column=1, sticky="w", padx=10)
        self.combo(dr, v["d"], [f"{i:02d}" for i in range(1, 32)], 4).pack(side="left")
        ttk.Label(dr, text="/").pack(side="left", padx=2)
        self.combo(dr, v["m"], [f"{i:02d}" for i in range(1, 13)], 4).pack(side="left")
        ttk.Label(dr, text="/").pack(side="left", padx=2)
        self.combo(dr, v["y"], [str(datetime.now().year + i) for i in range(4)], 6).pack(side="left")
        ttk.Label(dr, textvariable=day_var, width=5, anchor="w").pack(side="left", padx=(12, 0))

        ttk.Label(outer, text="Time (24h):").grid(row=3, column=0, sticky="w", pady=6)
        tr = ttk.Frame(outer)
        tr.grid(row=3, column=1, sticky="w", padx=10)
        self.combo(tr, v["h"], [f"{i:02d}" for i in range(24)], 4).pack(side="left")
        ttk.Label(tr, text=":").pack(side="left", padx=2)
        self.combo(tr, v["min"], [f"{i:02d}" for i in range(60)], 4).pack(side="left")

        ttk.Label(outer, text="Times here are in your device time zone.").grid(
            row=4, column=1, sticky="w", padx=10, pady=(2, 0)
        )

        def save():
            try:
                dt = datetime(
                    int(v["y"].get()), int(v["m"].get()), int(v["d"].get()),
                    int(v["h"].get()), int(v["min"].get())
                )
            except ValueError:
                messagebox.showwarning(
                    "Input Error",
                    "That date or time isn't valid. Please use numbers only and check the values.",
                    parent=win
                )
                return
            if dt <= datetime.now():
                messagebox.showwarning("Input Error", "The time must be in the future.", parent=win)
                return

            if is_shutdown:
                exe, arg = "shutdown.exe", "/s /t 60"
            else:
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("Input Error", "URL cannot be empty.", parent=win)
                    return
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                exe, arg = "explorer.exe", f'"{url}"'

            if self.register_task(name, exe, arg, dt):
                win.destroy()
                self.set_status("Task updated.")

        bf = ttk.Frame(outer)
        bf.grid(row=5, column=0, columnspan=2, pady=(14, 0))
        accent = {"style": "Accent.TButton"} if sv_ttk else {}
        ttk.Button(bf, text="Save", command=save, **accent).pack(side="left", padx=5)
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="left", padx=5)

        self.style_combo_popups()
        self.set_titlebar(win)

    # ---------- Black screen ----------
    def toggle_black(self):
        if self.black:
            self.close_black()
            return
        w = tk.Toplevel(self.root)
        w.configure(bg="black", cursor="none")
        w.attributes("-fullscreen", True)
        w.attributes("-topmost", True)
        w.bind("<Escape>", lambda e: self.close_black())
        w.bind("<Double-Button-1>", lambda e: self.close_black())
        w.protocol("WM_DELETE_WINDOW", self.close_black)
        w.focus_force()
        self.black = w
        self.black_btn.config(text="Turn Off Black Screen")
        if self.dim_var.get():
            self.root.after(150, self.apply_dim)

    def apply_dim(self):
        if self.black:
            self.dimmer.dim()

    def close_black(self):
        if self.black:
            self.black.destroy()
            self.black = None
        self.dimmer.restore()
        self.black_btn.config(text="Turn On Black Screen")


if __name__ == "__main__":
    enable_dpi_awareness()
    root = tk.Tk()
    WebSchedulerApp(root)
    root.mainloop()
