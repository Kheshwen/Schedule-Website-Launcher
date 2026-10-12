import os
import re
import json
import subprocess
import csv
import ctypes
from ctypes import wintypes
from io import StringIO
from datetime import datetime, timedelta
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox

TASK_PREFIX = "AutoWeb_"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # stops console flashing in the .exe
DT_FMT = "%d/%m/%Y %H:%M"
AUTO_REFRESH_MS = 15000
SETTINGS_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "WebsiteLauncher", "settings.json")

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
            u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            u.MonitorFromPoint.restype = ctypes.c_void_p
            hmon = u.MonitorFromPoint(wintypes.POINT(0, 0), 1)  # primary monitor (the one the overlay covers)
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


class WebSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Schedule Website Launcher V3.1")
        self.settings = load_settings()
        self.root.minsize(640, 560)
        self.apply_saved_geometry()

        self.black = None
        self.dimmer = Dimmer()
        self.args = {}
        self.rows = []
        self.overdue_tries = {}
        self.status_job = None
        col = self.settings.get("sort_col")
        self.sort_col = col if col in ("Task", "Next", "Status") else "Next"
        self.sort_rev = bool(self.settings.get("sort_rev", False))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.create_widgets()
        self.refresh_task_list()
        self.root.after(AUTO_REFRESH_MS, self.auto_refresh)

    # ---------- Settings / window ----------
    def apply_saved_geometry(self):
        self.root.geometry("720x620")
        m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", str(self.settings.get("geometry", "")))
        if m:
            w, h = max(int(m.group(1)), 640), max(int(m.group(2)), 560)
            x, y = int(m.group(3)), int(m.group(4))
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if -w + 100 < x < sw - 100 and 0 <= y < sh - 100:  # skip the position if it would be off-screen
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.root.geometry(f"{w}x{h}")
        if self.settings.get("zoomed"):
            self.root.state("zoomed")

    def on_close(self):
        self.close_black()  # makes sure brightness is restored
        try:
            state = self.root.state()
            if state != "normal":  # read the normal size, not the maximized one
                self.root.state("normal")
                self.root.update_idletasks()
            save_settings({
                "geometry": self.root.geometry(),
                "zoomed": state == "zoomed",
                "sort_col": self.sort_col,
                "sort_rev": self.sort_rev,
                "dim": self.dim_var.get(),
            })
        except Exception:
            pass
        self.root.destroy()

    def set_status(self, message):
        self.status_var.set(message)
        if self.status_job:
            self.root.after_cancel(self.status_job)
        self.status_job = self.root.after(6000, lambda: self.status_var.set(""))

    def combo(self, parent, var, values, width):
        return ttk.Combobox(parent, textvariable=var, values=values, width=width)

    def create_widgets(self):
        # ---- Status bar (packed first so it stays at the bottom) ----
        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken",
                  padding=(8, 3)).pack(side="bottom", fill="x")

        # ---- Schedule form ----
        f = ttk.LabelFrame(self.root, text="Schedule", padding=10)
        f.pack(fill="x", padx=10, pady=10)

        ttk.Label(f, text="Website URL:").grid(row=0, column=0, sticky="w", pady=5)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(f, textvariable=self.url_var, width=55)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="w", padx=5)

        d = datetime.now() + timedelta(minutes=5)
        self.day = tk.StringVar(value=f"{d.day:02d}")
        self.month = tk.StringVar(value=f"{d.month:02d}")
        self.year = tk.StringVar(value=str(d.year))
        self.hour = tk.StringVar(value=f"{d.hour:02d}")
        self.minute = tk.StringVar(value=f"{d.minute:02d}")

        ttk.Label(f, text="Date:").grid(row=1, column=0, sticky="w", pady=5)
        date_row = ttk.Frame(f)
        date_row.grid(row=1, column=1, sticky="w", padx=5)
        self.combo(date_row, self.day, [f"{i:02d}" for i in range(1, 32)], 4).pack(side="left")
        ttk.Label(date_row, text="/").pack(side="left")
        self.combo(date_row, self.month, [f"{i:02d}" for i in range(1, 13)], 4).pack(side="left")
        ttk.Label(date_row, text="/").pack(side="left")
        self.combo(date_row, self.year, [str(d.year + i) for i in range(4)], 6).pack(side="left")

        ttk.Label(f, text="Time (24h):").grid(row=2, column=0, sticky="w", pady=5)
        time_row = ttk.Frame(f)
        time_row.grid(row=2, column=1, sticky="w", padx=5)
        self.combo(time_row, self.hour, [f"{i:02d}" for i in range(24)], 4).pack(side="left")
        ttk.Label(time_row, text=":").pack(side="left")
        self.combo(time_row, self.minute, [f"{i:02d}" for i in range(60)], 4).pack(side="left")

        # Enter in any of the input boxes schedules the launch
        enter_widgets = [self.url_entry] + [c for row in (date_row, time_row)
                                            for c in row.winfo_children() if isinstance(c, ttk.Combobox)]
        for w in enter_widgets:
            w.bind("<Return>", lambda e: self.schedule_launch())

        btns = ttk.Frame(f)
        btns.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        ttk.Button(btns, text="Schedule Launch", command=self.schedule_launch).pack(side="left", padx=5)
        ttk.Button(btns, text="Schedule Shutdown", command=self.schedule_shutdown).pack(side="left", padx=5)
        ttk.Button(btns, text="Abort Shutdown Countdown", command=self.abort_shutdown).pack(side="left", padx=5)

        # ---- Black screen ----
        b = ttk.LabelFrame(self.root, text="Black Screen (audio keeps playing)", padding=10)
        b.pack(fill="x", padx=10, pady=(0, 10))
        self.black_btn = ttk.Button(b, text="Turn On Black Screen", command=self.toggle_black)
        self.black_btn.pack(side="left")
        self.dim_var = tk.BooleanVar(value=bool(self.settings.get("dim", True)))
        ttk.Checkbutton(b, text="Also lower brightness", variable=self.dim_var).pack(side="left", padx=10)
        ttk.Label(b, text="Esc or double-click to exit.").pack(side="left")

        # ---- Task list ----
        lf = ttk.LabelFrame(self.root, text="Scheduled Tasks (click a heading to sort, double-click a task to edit)", padding=10)
        lf.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(lf, columns=("Task", "Next", "Status"), show="headings", height=8, selectmode="extended")
        self.headings = {"Task": "Task / URL", "Next": "Next Run Time", "Status": "Status"}
        for col, w in (("Task", 300), ("Next", 140), ("Status", 80)):
            self.tree.heading(col, text=self.headings[col], command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=w, minwidth=80, stretch=(col == "Task"))
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

        bf = ttk.Frame(self.root)
        bf.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bf, text="Refresh", command=self.refresh_task_list).pack(side="left", padx=5)
        ttk.Button(bf, text="Clear Past Tasks", command=self.clear_past).pack(side="left", padx=5)
        ttk.Button(bf, text="Edit Selected", command=self.edit_selected).pack(side="left", padx=5)
        ttk.Button(bf, text="Delete Selected", command=self.delete_selected).pack(side="right", padx=5)

    # ---------- Inputs ----------
    def get_datetime(self):
        try:
            dt = datetime(int(self.year.get()), int(self.month.get()), int(self.day.get()),
                          int(self.hour.get()), int(self.minute.get()))
        except ValueError:
            messagebox.showwarning("Input Error", "That date or time isn't valid. Please use numbers only and check the values.")
            return None
        if dt <= datetime.now():
            messagebox.showwarning("Input Error", "The scheduled time must be in the future.")
            return None
        return dt

    def create_task(self, name, command, dt):
        cmd = ["schtasks", "/create", "/tn", name, "/tr", command, "/sc", "once",
               "/st", dt.strftime("%H:%M"), "/sd", dt.strftime("%d/%m/%Y"), "/f"]
        result = run(cmd)
        if result.returncode == 0:
            self.refresh_task_list()
            return True
        messagebox.showerror("System Error", f"Could not create task.\n\n{result.stderr}")
        return False

    # ---------- Schedule ----------
    def schedule_launch(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "URL cannot be empty.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        dt = self.get_datetime()
        if not dt:
            return

        domain = urlparse(url).netloc.replace(".", "_") or "WebLaunch"
        name = f"{TASK_PREFIX}{domain}_{datetime.now():%H%M%S}"
        if self.create_task(name, f'explorer.exe "{url}"', dt):
            self.set_status(f"Scheduled {url} for {dt:%d/%m/%Y %H:%M}.")
            self.url_var.set("")

    def schedule_shutdown(self):
        dt = self.get_datetime()
        if not dt:
            return
        name = f"{TASK_PREFIX}SHUTDOWN_{datetime.now():%H%M%S}"
        # 60-second countdown after it triggers, so you have time to abort
        if self.create_task(name, "shutdown.exe /s /t 60", dt):
            self.set_status(f"PC will start shutting down at {dt:%d/%m/%Y %H:%M} (60 sec countdown).")

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
        """Refreshes only when a Pending task's time has passed, so it doesn't run PowerShell for nothing."""
        now = datetime.now()
        due = []
        for name, shown, nxt, status in self.rows:
            if status == "Pending":
                try:
                    if datetime.strptime(nxt, DT_FMT) <= now:
                        due.append((name, nxt))
                except ValueError:
                    pass
        # a few tries, because Windows can take a few seconds to update a task after it runs
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
                return datetime.max  # finished tasks go last
        return (shown if self.sort_col == "Task" else status).lower()

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if col == self.sort_col else False
        self.sort_col = col
        self.render_tasks()

    def render_tasks(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for name, shown, nxt, status in sorted(self.rows, key=self.sort_key, reverse=self.sort_rev):
            self.tree.insert("", "end", iid=name, values=(shown, nxt or "-", status))
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
        failed = [n for n in names if run(["schtasks", "/delete", "/tn", n, "/f"]).returncode != 0]
        self.refresh_task_list()
        if failed:
            messagebox.showerror("Error", "Failed to delete:\n" + "\n".join(failed))
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
        names = [i for i in self.tree.get_children() if self.tree.item(i, "values")[2] == "Done"]
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
            d = datetime.strptime(values[1], DT_FMT)
        except ValueError:  # past task has no next run time
            d = datetime.now() + timedelta(minutes=5)

        win = tk.Toplevel(self.root)
        win.title("Edit Task")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text=values[0]).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5))

        url_var = tk.StringVar(value=self.args.get(name, "").strip().strip('"'))
        if not is_shutdown:
            ttk.Label(win, text="Website URL:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
            ttk.Entry(win, textvariable=url_var, width=45).grid(row=1, column=1, padx=10)

        v = {k: tk.StringVar(value=val) for k, val in (
            ("d", f"{d.day:02d}"), ("m", f"{d.month:02d}"), ("y", str(d.year)),
            ("h", f"{d.hour:02d}"), ("min", f"{d.minute:02d}"))}

        ttk.Label(win, text="Date:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        dr = ttk.Frame(win)
        dr.grid(row=2, column=1, sticky="w", padx=10)
        self.combo(dr, v["d"], [f"{i:02d}" for i in range(1, 32)], 4).pack(side="left")
        ttk.Label(dr, text="/").pack(side="left")
        self.combo(dr, v["m"], [f"{i:02d}" for i in range(1, 13)], 4).pack(side="left")
        ttk.Label(dr, text="/").pack(side="left")
        self.combo(dr, v["y"], [str(datetime.now().year + i) for i in range(4)], 6).pack(side="left")

        ttk.Label(win, text="Time (24h):").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        tr = ttk.Frame(win)
        tr.grid(row=3, column=1, sticky="w", padx=10)
        self.combo(tr, v["h"], [f"{i:02d}" for i in range(24)], 4).pack(side="left")
        ttk.Label(tr, text=":").pack(side="left")
        self.combo(tr, v["min"], [f"{i:02d}" for i in range(60)], 4).pack(side="left")

        def save():
            try:
                dt = datetime(int(v["y"].get()), int(v["m"].get()), int(v["d"].get()),
                              int(v["h"].get()), int(v["min"].get()))
            except ValueError:
                messagebox.showwarning("Input Error", "That date or time isn't valid. Please use numbers only and check the values.", parent=win)
                return
            if dt <= datetime.now():
                messagebox.showwarning("Input Error", "The time must be in the future.", parent=win)
                return
            cmd = ["schtasks", "/change", "/tn", name, "/st", dt.strftime("%H:%M"), "/sd", dt.strftime("%d/%m/%Y")]
            if not is_shutdown:
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("Input Error", "URL cannot be empty.", parent=win)
                    return
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                cmd += ["/tr", f'explorer.exe "{url}"']
            result = run(cmd)
            if result.returncode == 0:
                win.destroy()
                self.refresh_task_list()
                self.set_status("Task updated.")
            else:
                messagebox.showerror("System Error", f"Could not update task.\n\n{result.stderr}", parent=win)

        bf = ttk.Frame(win)
        bf.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="Save", command=save).pack(side="left", padx=5)
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="left", padx=5)

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
            self.root.after(150, self.apply_dim)  # after the overlay is on screen

    def apply_dim(self):
        if self.black:  # skip if it was already closed
            self.dimmer.dim()

    def close_black(self):
        if self.black:
            self.black.destroy()
            self.black = None
        self.dimmer.restore()
        self.black_btn.config(text="Turn On Black Screen")


if __name__ == "__main__":
    root = tk.Tk()
    WebSchedulerApp(root)
    root.mainloop()
