# Schedule Website Launcher v2.0

## Setup
1. Download this repo.
2. Double-click `setup.bat` in the 'src' folder.
3. If it shows `Build complete! ...`, it worked.

## Quick Start Guide
### 1. Scheduling a Website
1. Navigate to 'src/dist' and find 'scheduler.exe' application.
2. **Website URL:** Enter the link you want to open (e.g., `youtube.com`). The app will automatically add `https://` if you forget it.
3. **Date:** Enter the launch date in `DD/MM/YYYY` format (e.g., `21/08/2026`).
4. **Time:** Enter the launch time in 24-hour format (e.g., `14:30` for 2:30 PM).
5. Click **Schedule Launch**. A success popup will appear.

### 2. Managing & Canceling Tasks
* **View Tasks:** The bottom half of the application displays a list of all your active scheduled links. Click **Refresh List** to ensure it is up to date.
* **Cancel a Launch:** If you made a mistake or changed your mind, click on a task in the list to highlight it, then click **Delete Selected Task**.

## How to Uninstall
Because this is a standalone executable, it does not install deep into your system registry. To completely remove it:   

1. Open the app, highlight any active tasks in your list, and click **Delete Selected Task** so no hidden timers are left on your PC.
2. Close the application.
3. Delete the `scheduler.exe` file. That's it!

## What changed from V1.1
- **Visual Interface:** Completely replaced the command-line interface with a clean, easy-to-use graphical user interface (GUI) built with Tkinter.
- **Standalone App:** Packaged the entire Python script into a single `scheduler.exe` file. Users no longer need to install Python or run scripts to use the tool.
- **Task Management Dashboard:** Added a built-in window to view active tasks, refresh the task list, and easily delete scheduled launches directly from the app.
- **Safer Inputs:** Date and time inputs are now handled through visual form fields with strict popup validation, preventing accidental typos from crashing the scheduler.
- **Developer Tooling:** Added a `build.bat` script so developers can instantly re-compile the `.exe` file without typing out terminal commands.

## Restrictions
- PC Must Be Awake.
- Windows only.
- It will only open default browser.
- Strict formatting when you enter date and time.

## Future Improvement (Priority Scaled: Top to Bottom)
- Support MacOS and Linux (I'm also running Linux).
- Recurring schedules (daily/weekly), not just one-off.
- Add error logging to a file, not just console output.
- Unit tests for the date/time validation logic.
- A config file or .env for defaults instead of retyping URL each time.
- Minimize application to the system tray so the GUI doesn't have to stay open on the taskbar.
- Expand support to schedule and launch local files and applications, rather than just website URLs.
- Upgrade to CustomTkinter or PyQt for a modern UI with native dark mode.
- Convert to a local web dashboard (Flask/FastAPI) to allow remote scheduling from other devices.
- Use an internal Python scheduling library (like APScheduler) to bypass Windows schtasks entirely.

## Developer Note
- This is looking good...
