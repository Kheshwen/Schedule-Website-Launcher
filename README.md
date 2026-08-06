# Schedule Website Launcher V2.0

## Setup
1. Download 'code' folder.
2. Double-click `run_scheduler.bat` in the 'code' folder.
3. Give the website URL, launch time (HH:MM, 24-hr) and launch date (DD/MM/YYYY).
4. If it shows `SUCCESS: Scheduled...`, it worked.

## What changed from V1.0
- No more manual CMD — `run_scheduler.bat` runs the script for you.
- Time and date are now validated before scheduling (rejects bad formats and past dates).
- Command is passed safely to `schtasks` instead of as a raw shell string.

## Does it survive a restart?
Yes. `schtasks /create` registers the task directly with Windows Task Scheduler,
not with this Python script — so once it's scheduled, it will still fire even if
you shut down, restart or never open this folder again. You only need to run
the script once per scheduled link.

You can confirm it's saved anytime by opening Task Scheduler (`taskschd.msc`)
and looking for a task named `AutoWebLauncher`.

## Restrictions
- Only one scheduled link at a time and running the script again overwrites the
  previous `AutoWebLauncher` task (since `/f` force-overwrites by name).
- Windows only.

## Future Improvement (Priority Scaled - Desc)
- Input validation feedback loop (currently exits on bad input — could re-prompt instead).
- A simple GUI (Tkinter) instead of CMD prompts.
- Support multiple scheduled links at once (currently overwrites AutoWebLauncher each time).
- A "list/cancel scheduled tasks" option, so they don't have to dig into Task Scheduler manually.
- Support MacOS and Linux (I'm also running Linux).
- Recurring schedules (daily/weekly), not just one-off.
- Add error logging to a file, not just console output.
- Unit tests for the date/time validation logic.
- A config file or .env for defaults instead of retyping URL each time.

## Developer Word
I created it so i can have it launch twitch for twitch drops. Hope it's goes well.

