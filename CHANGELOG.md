# Changelog

## [3.0] - October 5 2026
### Added
- Date and time fields that can be typed in or picked from dropdowns.
- Edit Selected: change the URL, date or time of an existing task.
- Multi-select delete and a Clear Past Tasks button.
- Built-in fullscreen black screen that keeps audio playing (Esc or double-click to exit).
- Scheduled auto shutdown with a 60-second countdown and an abort button.
- Optional Inno Setup installer (`installer.iss`) and a custom app icon.
### Changed
- Task list now uses PowerShell to fetch only this app's tasks, so it loads faster.
- App is now built as a folder (`--onedir`) named `Website Launcher`, which Windows flags less often than a single `.exe`.
- `setup.bat` now installs PyInstaller if missing, cleans old build files and reports build failures.
- Background commands no longer flash console windows in the `.exe`.
- Updated `README.md` with the new setup, features and restrictions.

## [2.0] - August 21 2026
### Added
- Complete Tkinter graphical user interface (GUI).
- Task management: View, list, and delete scheduled tasks directly in the app.
- Packaged as a standalone Windows `.exe` file.
- `build.bat` script to easily automate the PyInstaller compilation process for developers.
### Changed
- Converted command-line inputs into visual form fields.
- Date and time formats are strictly validated via UI popups.
- Updated `README.md` with new `.exe` setup instructions and updated `.gitignore` for PyInstaller.

## [1.1] - August 6 2026
### Added
- Input validation for date and time fields.
- `run_scheduler.bat` wrapper to automate script execution.
### Fixed
- Addressed command injection vulnerability by passing `cmd` as an array to `

## [1.0] - July 23 2026
### Added
- Initial command-line release utilizing Windows `schtasks`.
