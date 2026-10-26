import tkinter as tk
from tkinter import ttk

from launcher import APP_VERSION
from launcher.logs import setup_logging
from launcher.ui import WebSchedulerApp, enable_dpi_awareness

def main():
    enable_dpi_awareness()
    log = setup_logging()
    log.info("Starting Schedule Website Launcher %s", APP_VERSION)
    try:
        root = tk.Tk()
        
        # Keep the scaling multiplier
        root.tk.call('tk', 'scaling', 2.0) 
        
        # Initialize the app and sv-ttk theme first
        WebSchedulerApp(root)
        
        # Override the sv-ttk font size globally AFTER initialization
        style = ttk.Style()
        style.configure('.', font=('Segoe UI', 13)) # '.' applies to all widgets
        
        root.mainloop()
    except Exception:
        log.exception("Fatal error")
        raise
    log.info("Closed normally")

if __name__ == "__main__":
    main()