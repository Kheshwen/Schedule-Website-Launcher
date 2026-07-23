import os
import subprocess
import sys


def schedule_task():
    print("=== Windows Background Link Scheduler ===")
    url = input("Enter website URL (e.g., https://google.com): ").strip()
    target_time = input(
        "Enter launch time in 24-hr format (HH:MM, e.g., 14:30): "
    ).strip()
    target_date = input(
        "Enter launch date in (YYYY-MM-DD, e.g., 2006-04-05): "

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    task_name = "AutoWebLauncher"

    # Command that Windows will run silently in the background
    action_cmd = f'cmd.exe /c start "" "{url}"'

    # Build the schtasks command
    # /sc once = Run once
    # /st HH:MM = Start time
    # /sd YYYY-MM-DD = Start date
    # /f = Force overwrite if a task with this name already exists
    cmd = f'schtasks /create /tn "{task_name}" /tr "{action_cmd}" /sc once /st {target_time} /sd {target_date}/f'

    print("\nRegistering background task with Windows...")

    # Execute the Windows command silently
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"SUCCESS: Scheduled '{url}' for {target_time}!")
        print("You can close this terminal now. Windows will launch it.")
    else:
        print("ERROR: Could not create schedule.")
        print(result.stderr)


if __name__ == "__main__":
    schedule_task()
