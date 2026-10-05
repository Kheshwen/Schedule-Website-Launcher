# Schedule Website Launcher v3.0

## Setup
1. Download this repo.
2. Make sure `icon.ico` (a real `.ico` file) is in the `src` folder.
3. Double-click `setup.bat` in the `src` folder.
4. If it shows `Build complete! ...`, it worked. The app is in `src/dist/Website Launcher/`.

### Optional: Build an Installer
1. Install [Inno Setup](https://jrsoftware.org/isinfo.php) (free).
2. Open `installer.iss` in Inno Setup and press **Ctrl+F9**.
3. Your installer is created at `src/Output/WebsiteLauncher_Setup.exe`.

## Quick Start Guide
### 1. Scheduling a Website
1. Open `Website Launcher.exe` (from `src/dist/Website Launcher`, or from the Start Menu if you used the installer).
2. **Website URL:** Enter the link you want to open (e.g., `youtube.com`). The app will automatically add `https://` if you forget it.
3. **Date and Time:** Pick the day, month, year, hour and minute from the dropdowns (24-hour format). They default to 5 minutes from now.
4. Click **Schedule Launch**. A success popup will appear.

### 2. Scheduling a Shutdown
1. Pick the date and time using the same dropdowns.
2. Click **Schedule Shutdown**.
3. When the time arrives, Windows starts a 60-second countdown. Click **Abort Shutdown Countdown** to cancel it.

### 3. Managing Tasks
* **View Tasks:** The bottom half of the app lists all your scheduled tasks as *Pending* or *Done*. Click **Refresh** to update it.
* **Edit a Task:** Select one task, click **Edit Selected**, change the URL, date or time, then press **Save**. Shutdown tasks only let you change the date and time.
* **Delete Tasks:** Select one or more tasks, then click **Delete Selected**.
* **Clear Past Tasks:** Click **Clear Past Tasks** to remove everything that has already run.

### 4. Black Screen
1. Click **Turn On Black Screen** to cover the screen with black. The website keeps playing, so you can still hear it.
2. Press **Esc** or **double-click** to turn it off.

## How to Uninstall
1. Open the app, select all your tasks and click **Delete Selected** so no hidden timers are left on your PC.
2. Close the application.
3. If you used the installer, remove it from Windows **Settings > Installed apps**. Otherwise, delete the `Website Launcher` folder.

## What changed from V2.0
- **Date and Time Pickers:** Dropdowns replace typing, so invalid formats can't happen.
- **Edit Tasks:** Change the URL, date or time of an existing task without deleting it.
- **Delete and Clear:** Delete multiple tasks at once and clear all past tasks in one click.
- **Built-in Black Screen:** A fullscreen black overlay that can be toggled any time while the audio keeps playing.
- **Auto Shutdown:** Schedule a PC shutdown with a 60-second countdown and an abort button.
- **Faster Task List:** The list now uses PowerShell to fetch only this app's tasks instead of scanning all of them.
- **Folder Build and Installer:** The app is now built as a folder (`--onedir`) instead of a single `.exe`, which Windows flags less often, with an optional Inno Setup installer.

## Restrictions
- PC must be awake.
- Windows 10 or 11 only.
- Built for English Windows with Malaysian date settings (DD/MM/YYYY). Other regional settings may break scheduling.
- It will only open the default browser.
- The black screen covers the main monitor only, and the browser must stay open behind it for the audio to keep playing.
- Windows Defender may flag the app as a virus. This is a common false positive with PyInstaller apps. You can add the app folder as an exclusion in Windows Security, or report it as a false positive to Microsoft.

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
