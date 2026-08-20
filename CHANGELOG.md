# Changelog

## [2.0] 
### Added
- Complete Tkinter graphical user interface (GUI).
- Task management: View, list, and delete scheduled tasks directly in the app.
- Packaged as a standalone Windows `.exe` file.
- `build.bat` script to easily automate the PyInstaller compilation process for developers.
### Changed
- Converted command-line inputs into visual form fields.
- Date and time formats are strictly validated via UI popups.
- Updated `README.md` with new `.exe` setup instructions and updated `.gitignore` for PyInstaller.

## [1.1]
### Added
- Input validation for date and time fields.
- `run_scheduler.bat` wrapper to automate script execution.
### Fixed
- Addressed command injection vulnerability by passing `cmd` as an array to `subprocess`.

## [1.0] 
### Added
- Initial command-line release utilizing Windows `schtasks`.
