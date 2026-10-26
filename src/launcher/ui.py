"""The window. All scheduling, validation and time logic lives in the other modules."""
import ctypes
import logging
import os
import re
import tkinter as tk
import traceback
from ctypes import wintypes
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

from . import APP_VERSION
from .dimmer import Dimmer
from .logs import log_path
from .paths import app_data_dir, resource_path
from .settings import load_settings, save_settings
from .tasks import TaskService, abort_shutdown
from .timeutil import (DEVICE, ZoneBook, convert_to_device, filter_entries, relative_text,
                       resolve_zone, zone_issue)
from .validation import InvalidURL, make_task_name, normalize_url

try:
    import sv_ttk  # modern light/dark theme (optional: the app still works without it)
except Exception:
    sv_ttk = None

log = logging.getLogger("launcher.ui")

DT_FMT = "%d/%m/%Y %H:%M"
AUTO_REFRESH_MS = 15000
SETTINGS_FILE = os.path.join(app_data_dir(), "settings.json")

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


NAV_KEYS = {
    "Return", "Tab", "Up", "Down", "Left", "Right", "Escape", "Home", "End",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"
}


class WebSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Schedule Website Launcher V{APP_VERSION}")
        self.service = TaskService()
        self.settings = load_settings(SETTINGS_FILE)
        self.root.report_callback_exception = self.on_callback_error
        self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.minsize(self.px(680), self.px(620))
        self.apply_saved_geometry()
        try:
            self.root.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            pass

        self.black = None
        self.dimmer = Dimmer()
        self.tasks = {}
        self.overdue_tries = {}
        self.status_job = None
        self.combos = []
        self.zones = ZoneBook()
        self.tz_editing = False
        self.mode = "light"

        col = self.settings.get("sort_col")
        self.sort_col = col if col in ("Task", "Next", "Status") else "Next"
        self.sort_rev = bool(self.settings.get("sort_rev", False))

        pref = self.settings.get("theme")
        self.theme_pref = pref if pref in ("system", "light", "dark") else "system"

        self.zone_names = self.zones.names
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
        if self.zones.incomplete:
            self.set_status("Some time zones are unavailable. Run: pip install tzdata")

    def on_callback_error(self, exc, val, tb):
        log.error("Unhandled error in the window: %s", "".join(traceback.format_exception(exc, val, tb)))
        try:
            self.set_status(f"Something went wrong. Details are saved in {os.path.basename(log_path())}")
        except Exception:
            pass

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
            save_settings(SETTINGS_FILE, {
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
                
        # --- SCALING OVERRIDE START ---
        try:
            import tkinter.font as tkfont
            # 1. Scale every font proportionally by 1.2x
            scale_factor = 1.2 
            for font_name in tkfont.names():
                f = tkfont.nametofont(font_name)
                current_size = f.cget("size")
                
                # Apply the multiplier, keeping negative pixel sizes intact
                new_size = int(current_size * scale_factor)
                if new_size == 0:
                    new_size = 14 if current_size > 0 else -18
                    
                f.configure(size=new_size)
            
            # 2. Adjust Treeview row height to fit the scaled text
            style = ttk.Style()
            style.configure("Treeview", rowheight=self.px(36))
        except Exception:
            pass
        # --- SCALING OVERRIDE END ---

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
        return self.zones.get(key)

    def tz_entries(self, ref):
        return self.zones.entries(ref)

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
            local = convert_to_device(dt, tz)
            note = "  (this time happens twice, the first one is used)" if issue == "ambiguous" else ""
        rel = relative_text(local, datetime.now())
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
        self.tz_key = resolve_zone(self.tz_var.get(), self.zone_names)
        self.tz_combo["values"] = filter_entries(self.tz_entries(self.ref_datetime()), self.tz_var.get())
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
        tz = self.zone(self.tz_key) if self.tz_key not in (None, DEVICE) else None
        now = datetime.now(tz).replace(tzinfo=None) if tz else datetime.now()
        base = max(self.entered_datetime() or now, now)
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

    def selected_task(self):
        sel = self.tree.selection()
        return self.tasks.get(sel[0]) if sel else None

    def open_selected_now(self):
        for name in self.tree.selection():
            task = self.tasks.get(name)
            if not task or task.kind != "launch":
                continue
            try:
                url = normalize_url(task.url)
            except InvalidURL:
                self.set_status("That task's link isn't a valid web address, so it wasn't opened.")
                continue
            os.startfile(url)

    def copy_selected_url(self):
        task = self.selected_task()
        if task and task.url:
            self.root.clipboard_clear()
            self.root.clipboard_append(task.url)
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
            dt = convert_to_device(dt, tz)
        if dt <= datetime.now():
            messagebox.showwarning("Input Error", "The scheduled time must be in the future.")
            return None
        return dt

    def finish(self, result, what):
        """Shows an error if the task service failed. Returns True on success."""
        self.refresh_task_list()
        if not result.ok:
            messagebox.showerror("System Error", f"Could not {what}.\n\n{result.error}")
        return result.ok

    # ---------- Schedule ----------
    def schedule_launch(self):
        try:
            url = normalize_url(self.url_entry.value())
        except InvalidURL as exc:
            messagebox.showwarning("Input Error", str(exc))
            return
        dt = self.get_datetime()
        if not dt:
            return
        name = make_task_name(urlsplit(url).hostname, datetime.now())
        if self.finish(self.service.register_launch(name, url, dt), "schedule the task"):
            self.set_status(f"Scheduled {url} for {dt:%a %d/%m/%Y %H:%M} (your device time).")
            self.url_entry.clear()

    def schedule_shutdown(self):
        dt = self.get_datetime()
        if not dt:
            return
        name = make_task_name("", datetime.now(), shutdown=True)
        if self.finish(self.service.register_shutdown(name, dt), "schedule the shutdown"):
            self.set_status(f"PC will start shutting down at {dt:%a %d/%m/%Y %H:%M} (60 sec countdown).")

    def abort_shutdown(self):
        if abort_shutdown():
            self.set_status("Shutdown countdown cancelled.")
        else:
            self.set_status("No shutdown countdown is running right now.")

    # ---------- Task list ----------
    def refresh_task_list(self):
        tasks, result = self.service.list_tasks()
        if result.ok:
            self.tasks = {t.name: t for t in tasks}
        else:
            self.set_status(result.error)
        self.render_tasks()

    def auto_refresh(self):
        now = datetime.now()
        due = [
            (t.name, t.next_run) for t in self.tasks.values()
            if t.next_run and t.next_run <= now
        ]
        fresh = [k for k in due if self.overdue_tries.get(k, 0) < 4]
        if fresh:
            for k in fresh:
                self.overdue_tries[k] = self.overdue_tries.get(k, 0) + 1
            self.refresh_task_list()
        self.root.after(AUTO_REFRESH_MS, self.auto_refresh)

    def sort_key(self, task):
        if self.sort_col == "Next":
            return task.next_run or datetime.max
        return (task.label if self.sort_col == "Task" else task.status).lower()

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if col == self.sort_col else False
        self.sort_col = col
        self.render_tasks()

    def render_tasks(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for task in sorted(self.tasks.values(), key=self.sort_key, reverse=self.sort_rev):
            day = task.next_run.strftime("%a") if task.next_run else "-"
            nxt = task.next_run.strftime(DT_FMT) if task.next_run else "-"
            self.tree.insert(
                "", "end", iid=task.name, values=(task.label, day, nxt, task.status),
                tags=("pending" if task.status == "Pending" else "done",)
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
        if self.finish(self.service.delete(names), "delete the tasks"):
            self.set_status(f"Deleted {len(names)} task(s).")

    def delete_selected(self):
        names = list(self.tree.selection())
        if not names:
            self.set_status("Select a task from the list first.")
            return
        if messagebox.askyesno("Confirm Deletion", f"Delete {len(names)} selected task(s)?"):
            self.delete_tasks(names)

    def clear_past(self):
        names = [t.name for t in self.tasks.values() if t.status == "Done"]
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
        task = self.tasks.get(sel[0])
        if task is None or task.kind == "other":
            self.set_status("That task can't be edited here.")
            return
        name = task.name
        is_shutdown = task.kind == "shutdown"
        d = task.next_run or datetime.now() + timedelta(minutes=5)

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
        ttk.Label(outer, text=task.label).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        url_var = tk.StringVar(value=task.url)
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
                result = self.service.register_shutdown(name, dt)
            else:
                try:
                    url = normalize_url(url_var.get())
                except InvalidURL as exc:
                    messagebox.showwarning("Input Error", str(exc), parent=win)
                    return
                result = self.service.register_launch(name, url, dt)

            if self.finish(result, "update the task"):
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
