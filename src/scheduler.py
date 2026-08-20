import subprocess
import sys
import csv
from io import StringIO
from datetime import datetime
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox

TASK_PREFIX = "AutoWeb_"

class WebSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Schedule Website Launcher V2.0")
        self.root.geometry("600x450")
        self.root.resizable(False, False)

        self.create_widgets()
        self.refresh_task_list()

    def create_widgets(self):
        # Input Form
        input_frame = ttk.LabelFrame(self.root, text="Schedule New Website", padding=(10, 10))
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="Website URL:").grid(row=0, column=0, sticky="w", pady=5)
        self.url_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.url_var, width=50).grid(row=0, column=1, columnspan=2, sticky="w", pady=5, padx=5)

        ttk.Label(input_frame, text="Date (DD/MM/YYYY):").grid(row=1, column=0, sticky="w", pady=5)
        self.date_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.date_var, width=15).grid(row=1, column=1, sticky="w", pady=5, padx=5)

        ttk.Label(input_frame, text="Time (HH:MM):").grid(row=2, column=0, sticky="w", pady=5)
        self.time_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.time_var, width=15).grid(row=2, column=1, sticky="w", pady=5, padx=5)

        ttk.Button(input_frame, text="Schedule Launch", command=self.schedule_task).grid(row=3, column=0, columnspan=3, pady=10)

        # Task List
        list_frame = ttk.LabelFrame(self.root, text="Scheduled Tasks", padding=(10, 10))
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        columns = ("Task Name", "Next Run Time", "Status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=8)
        
        self.tree.heading("Task Name", text="Task Name")
        self.tree.column("Task Name", width=250)
        self.tree.heading("Next Run Time", text="Next Run Time")
        self.tree.column("Next Run Time", width=150)
        self.tree.heading("Status", text="Status")
        self.tree.column("Status", width=100)

        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        ttk.Button(btn_frame, text="Refresh List", command=self.refresh_task_list).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Delete Selected Task", command=self.delete_selected_task).pack(side="right", padx=5)

    def validate_inputs(self):
        url = self.url_var.get().strip()
        date_str = self.date_var.get().strip()
        time_str = self.time_var.get().strip()

        if not url:
            messagebox.showwarning("Input Error", "URL cannot be empty.")
            return None
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed_date = datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError:
            messagebox.showwarning("Input Error", "Invalid date format. Use DD/MM/YYYY.")
            return None

        try:
            parsed_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            messagebox.showwarning("Input Error", "Invalid time format. Use HH:MM (24-hr).")
            return None

        target_dt = datetime.combine(parsed_date, parsed_time)
        if target_dt <= datetime.now():
            messagebox.showwarning("Input Error", "The scheduled time must be in the future.")
            return None

        return url, parsed_date.strftime("%d/%m/%Y"), parsed_time.strftime("%H:%M")

    def schedule_task(self):
        inputs = self.validate_inputs()
        if not inputs: return
        url, date_str, time_str = inputs

        domain = urlparse(url).netloc.replace(".", "_") or "WebLaunch"
        timestamp = datetime.now().strftime("%H%M%S")
        task_name = f"{TASK_PREFIX}{domain}_{timestamp}"

        action_cmd = f'explorer.exe "{url}"'
        cmd = ["schtasks", "/create", "/tn", task_name, "/tr", action_cmd, "/sc", "once", "/st", time_str, "/sd", date_str, "/f"]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            messagebox.showinfo("Success", f"Scheduled '{url}' successfully!")
            self.url_var.set("")
            self.time_var.set("")
            self.refresh_task_list()
        else:
            messagebox.showerror("System Error", f"Could not create task.\n\n{result.stderr}")

    def refresh_task_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        cmd = ["schtasks", "/query", "/fo", "CSV", "/nh"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        except Exception:
            return

        if result.returncode != 0: return

        f = StringIO(result.stdout)
        reader = csv.reader(f)
        
        for row in reader:
            if len(row) >= 3:
                clean_name = row[0].lstrip('\\')
                if clean_name.startswith(TASK_PREFIX):
                    self.tree.insert("", "end", values=(clean_name, row[1], row[2]))

    def delete_selected_task(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showinfo("Selection Required", "Please select a task from the list.")
            return

        task_name = self.tree.item(selected_item, "values")[0]
        if messagebox.askyesno("Confirm Deletion", f"Cancel task:\n{task_name}?"):
            cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
            if subprocess.run(cmd, capture_output=True, text=True).returncode == 0:
                self.refresh_task_list()
                messagebox.showinfo("Deleted", "Task cancelled successfully.")
            else:
                messagebox.showerror("Error", "Failed to delete task.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WebSchedulerApp(root)
    root.mainloop()
