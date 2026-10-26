# Schedule Website Launcher v3.3

## Setup
1. Download this repo.
2. Make sure `icon.ico` (a real `.ico` file) is in the `src` folder.
3. Double-click `setup.bat` in the `src` folder. It installs what it needs from `requirements.txt`.
4. If it shows `Done. The app is in dist\Website Launcher\`, it worked. The app is in `src/dist/Website Launcher/`.

### Optional: Build an Installer
1. Install [Inno Setup](https://jrsoftware.org/isinfo.php) (free).
2. Open `installer.iss` in Inno Setup and press **Ctrl+F9**.
3. Your installer is created at `src/Output/WebsiteLauncher_Setup.exe`.

## Quick Start Guide
### 1. Scheduling a Website
1. Open `Website Launcher.exe` (from `src/dist/Website Launcher`, or from the Start Menu if you used the installer).
2. **Website URL:** Enter the link you want to open (e.g., `youtube.com`). The app will automatically add `https://` if you forget it.
3. **Date and Time:** Type the day, month, year, hour and minute, or pick them from the dropdowns (24-hour format). They default to 5 minutes from now. The day of the week appears next to the date. **+15m**, **+1h** and **+1d** move the time forward.
4. **Time Zone:** Leave it on *Device time*, or type or pick another one (e.g. `ET`, `PT`, `IST` or `Tokyo`). The preview shows when the task will run on your device. The app handles daylight saving and warns you if a time doesn't exist or happens twice.
5. Click **Schedule Launch**, or press **Enter** in the URL, date or time boxes. A confirmation appears in the status bar at the bottom.

### 2. Scheduling a Shutdown
1. Set the date and time the same way.
2. Click **Schedule Shutdown**.
3. When the time arrives, Windows starts a 60-second countdown. Click **Abort Shutdown Countdown** to cancel it.

### 3. Managing Tasks
* **View Tasks:** The bottom half of the app lists your scheduled tasks with the website URL, next run time and status (*Pending* or *Done*). The list updates by itself when a task runs, or click **Refresh** to update it manually.
* **Sort Tasks:** Click a column heading to sort by task, time or status. Click it again to reverse the order.
* **Edit a Task:** Double-click a task, or select it and click **Edit Selected**. Change the URL, date or time, then press **Save**. Shutdown tasks only let you change the date and time.
* **Right-Click Menu:** Right-click a task for Open URL Now, Copy URL, Edit and Delete.
* **Delete Tasks:** Select one or more tasks, then click **Delete Selected** or press the **Delete** key.
* **Clear Past Tasks:** Click **Clear Past Tasks** to remove everything that has already run.

### 4. Black Screen
1. Click **Turn On Black Screen** to cover the screen with black. The website keeps playing, so you can still hear it.
2. Tick **Also lower brightness** to make it darker. The app lowers your real screen brightness and restores it when you turn the black screen off or close the app.
3. Press **Esc** or **double-click** to turn it off.

### 5. Window and Settings
* **Resize:** Drag the window edges or use the maximize button.
* **Theme:** Choose System, Light or Dark in the bottom right. System follows Windows.
* **Saved Settings:** The app remembers your window size, position, sort order, time zone, theme and the brightness option. They are stored in `%APPDATA%\WebsiteLauncher\settings.json`.

## How to Uninstall
1. Open the app, select all your tasks and click **Delete Selected** so no hidden timers are left on your PC.
2. Close the application.
3. If you used the installer, remove it from Windows **Settings > Installed apps**. Otherwise, delete the `Website Launcher` folder.
4. Optional: delete the `%APPDATA%\WebsiteLauncher` folder to remove the saved settings and the log file.

## Running the Tests
1. `pip install -r requirements-dev.txt`
2. `cd src` then `pytest`

Errors and activity are written to `%APPDATA%\WebsiteLauncher\launcher.log`. Only website host names are logged, never full links.

## What changed from V3.2
- **Safer Links:** Links are rebuilt and checked. Only `http` and `https` are accepted, and anything that could break out of the scheduled command is refused or encoded.
- **Safer Commands:** Everything passed to PowerShell is quoted safely, programs run from their full Windows paths, and commands time out after 30 seconds.
- **Correct Task Types:** A task is a shutdown or a website based on the program it runs, not its name.
- **Safer Settings:** `settings.json` is validated and saved safely.
- **Log File:** Errors and activity are saved to `launcher.log`.
- **Tests:** 45 unit tests, run automatically on GitHub for Windows and Linux.
- **Cleaner Code:** Split into a `launcher` package instead of one large file.

## Restrictions
- Website launches wake the PC and run late if the time was missed. Shutdown tasks never run late.
- Windows 10 or 11 only.
- Built for English Windows. Scheduling no longer depends on the regional date format.
- Time zone names need the `tzdata` package (installed by `setup.bat`). Without it, only regions without daylight saving are listed.
- It will only open the default browser.
- The black screen covers the main monitor only, and the browser must stay open behind it for the audio to keep playing.
- Lowering brightness only works on monitors that support DDC/CI and on laptop screens. Otherwise, you only get the black overlay.
- Windows Defender may flag the app as a virus. This is a common false positive with PyInstaller apps. You can add the app folder as an exclusion in Windows Security, or report it as a false positive to Microsoft.

## Future Improvement (Priority Scaled: Top to Bottom)
- Support MacOS and Linux (I'm also running Linux).
- Recurring schedules (daily/weekly), not just one-off.
- Run PowerShell calls in the background so the window never pauses.
- Automatic GitHub releases with the installer attached.
- Saved favourite URLs so you don't have to retype them (window settings are already saved, but URLs are not).
- Minimize application to the system tray so the GUI doesn't have to stay open on the taskbar.
- Expand support to schedule and launch local files and applications, rather than just website URLs.
- Upgrade to CustomTkinter or PyQt for a modern UI with native dark mode.
- Convert to a local web dashboard (Flask/FastAPI) to allow remote scheduling from other devices.
- Use an internal Python scheduling library (like APScheduler) to bypass Windows schtasks entirely.

## Developer Note
- This is looking good...