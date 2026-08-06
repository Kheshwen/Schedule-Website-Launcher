import subprocess
import sys
from datetime import datetime


def schedule_task():
    print("=== Windows Background Link Scheduler ===")
    url = input("Enter website URL (e.g., https://google.com): ").strip()
    target_time = input(
        "Enter launch time in 24-hr format (HH:MM, e.g., 14:30): "
    ).strip()
    target_date = input(
        "Enter launch date (DD/MM/YYYY, e.g., 05/04/2026): "
	).strip()
	

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        datetime.strptime(target_time, "%H:%M")
    except ValueError:
        print("ERROR: Time must be in HH:MM 24-hour format (e.g., 14:30).")
        sys.exit(1)

    try:
        parsed_date = datetime.strptime(target_date, "%d/%m/%Y")
    except ValueError:
        print("ERROR: Date must be in DD/MM/YYYY format (e.g., 05/04/2026).")
        sys.exit(1)

    if parsed_date.date() < datetime.now().date():
        print("ERROR: That date is in the past.")
        sys.exit(1)

    normalized_date = parsed_date.strftime("%d/%m/%Y")

    task_name = "AutoWebLauncher"

    # Command that Windows will run silently in the background
    action_cmd = f'explorer.exe "{url}"'

    # Build the schtasks command
    # /sc once = Run once
    # /st HH:MM = Start time
    # /sd YYYY-MM-DD = Start date
    # /f = Force overwrite if a task with this name already exists
    
	cmd = [
	    "schtasks", "/create",
	    "/tn", task_name,
	    "/tr", action_cmd,
	    "/sc", "once",
	    "/st", target_time,
	    "/sd", normalized_date,
	    "/f",
	]

    print("\nRegistering background task with Windows...")

    # Execute the Windows command silently
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"SUCCESS: Scheduled '{url}' for {target_time} on {normalized_date}!")
        print("You can close this terminal now. Windows will launch it.")
    else:
        print("ERROR: Could not create schedule.")
        print(result.stderr)
		print(
            "\nTip: if this mentions an invalid date format, your Windows "
            "locale may not be DD/MM/YYYY — check Settings > Time & "
            "Language > Language & Region > Regional format."
        )


if __name__ == "__main__":
    schedule_task()
