import subprocess
import csv
from io import StringIO
from datetime import datetime, timedelta
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox

TASK_PREFIX = "AutoWeb_"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # stops console flashing in the .exe

# Filters by name inside PowerShell, so it only fetches our tasks (much faster)
PS_LIST = (
    "Get-ScheduledTask -TaskName 'AutoWeb_*' -ErrorAction SilentlyContinue | ForEach-Object { "
    "$i = $_ | Get-ScheduledTaskInfo; $n = ''; "
    "if ($i.NextRunTime -and $i.NextRunTime.Year -gt 2000) { $n = $i.NextRunTime.ToString('dd/MM/yyyy HH:mm') }; "
    "[pscustomobject]@{Name=$_.TaskName; Next=$n; Args=$_.Actions[0].Arguments} } | ConvertTo-Csv -NoTypeInformation"
)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="ignore", creationflags=NOWIN)


class WebSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Schedule Website Launcher V3.0")
        self.root.geometry("640x580")
        self.root.resizable(False, False)
        self.black = None

        self.create_widgets()
        self.refresh_task_list()

    def combo(self, parent, var, values, width):
        return ttk.Combobox(parent, textvariable=var, values=values, width=width)

    def create_widgets(self):
        # ---- Schedule form ----
        f = ttk.LabelFrame(self.root, text="Schedule", padding=10)
        f.pack(fill="x", padx=10, pady=10)

        ttk.Label(f, text="Website URL:").grid(row=0, column=0, sticky="w", pady=5)
        self.url_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.url_var, width=55).grid(row=0, column=1, columnspan=2, sticky="w", padx=5)

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
        ttk.Label(b, text="Press Esc or double-click to turn it off.").pack(side="left", padx=10)

        # ---- Task list ----
        lf = ttk.LabelFrame(self.root, text="Scheduled Tasks", padding=10)
        lf.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(lf, columns=("Task", "Next", "Status"), show="headings", height=8, selectmode="extended")
        for col, text, w in (("Task", "Task Name", 270), ("Next", "Next Run Time", 140), ("Status", "Status", 80)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

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
            messagebox.showinfo("Success", f"Scheduled '{url}' for {dt:%d/%m/%Y %H:%M}.")
            self.url_var.set("")

    def schedule_shutdown(self):
        dt = self.get_datetime()
        if not dt:
            return
        name = f"{TASK_PREFIX}SHUTDOWN_{datetime.now():%H%M%S}"
        # 60-second countdown after it triggers, so you have time to abort
        if self.create_task(name, "shutdown.exe /s /t 60", dt):
            messagebox.showinfo("Success", f"PC will start shutting down at {dt:%d/%m/%Y %H:%M} (60 sec countdown).")

    def abort_shutdown(self):
        result = run(["shutdown", "/a"])
        if result.returncode == 0:
            messagebox.showinfo("Aborted", "Shutdown countdown cancelled.")
        else:
            messagebox.showinfo("Nothing to abort", "No shutdown countdown is running right now.")

    # ---------- Task list ----------
    def refresh_task_list(self):
        self.tree.delete(*self.tree.get_children())
        self.args = {}
        try:
            result = run(["powershell", "-NoProfile", "-Command", PS_LIST])
        except Exception:
            return
        if result.returncode != 0 or not result.stdout.strip():
            return
        for row in csv.DictReader(StringIO(result.stdout)):
            name, nxt = row.get("Name", ""), row.get("Next", "")
            self.args[name] = row.get("Args", "")
            self.tree.insert("", "end", iid=name, values=(name, nxt or "-", "Pending" if nxt else "Done"))

    def delete_tasks(self, names):
        failed = [n for n in names if run(["schtasks", "/delete", "/tn", n, "/f"]).returncode != 0]
        self.refresh_task_list()
        if failed:
            messagebox.showerror("Error", "Failed to delete:\n" + "\n".join(failed))

    def delete_selected(self):
        names = list(self.tree.selection())
        if not names:
            messagebox.showinfo("Selection Required", "Please select a task from the list.")
            return
        if messagebox.askyesno("Confirm Deletion", f"Delete {len(names)} selected task(s)?"):
            self.delete_tasks(names)

    def clear_past(self):
        names = [i for i in self.tree.get_children() if self.tree.item(i, "values")[2] == "Done"]
        if not names:
            messagebox.showinfo("Nothing to clear", "There are no past tasks.")
            return
        if messagebox.askyesno("Clear Past Tasks", f"Delete {len(names)} finished task(s)?"):
            self.delete_tasks(names)

    # ---------- Edit ----------
    def edit_selected(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Selection Required", "Please select one task to edit.")
            return
        name = sel[0]
        is_shutdown = "SHUTDOWN" in name
        try:
            d = datetime.strptime(self.tree.item(name, "values")[1], "%d/%m/%Y %H:%M")
        except ValueError:  # past task has no next run time
            d = datetime.now() + timedelta(minutes=5)

        win = tk.Toplevel(self.root)
        win.title("Edit Task")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text=name).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5))

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

    def close_black(self):
        if self.black:
            self.black.destroy()
            self.black = None
        self.black_btn.config(text="Turn On Black Screen")


if __name__ == "__main__":
    root = tk.Tk()
    WebSchedulerApp(root)
    root.mainloop()
