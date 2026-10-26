"""Lowers the real screen brightness while the black screen is on.

DDC/CI for external monitors, WMI for laptop screens. Windows only; every call is wrapped so a
monitor that doesn't support it just means no dimming.
"""
import ctypes
import logging
from ctypes import wintypes

from .tasks import run_powershell

log = logging.getLogger("launcher.dimmer")

WMI_GET = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness"
WMI_SET = (
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
    "ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName WmiSetBrightness -Arguments @{Timeout=1; Brightness=%d} }"
)


class PHYSICAL_MONITOR(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("handle", ctypes.c_void_p), ("desc", wintypes.WCHAR * 128)]


class Dimmer:
    def __init__(self):
        self.mode = None
        self.saved = None
        self.monitors = None

    def _dxva2(self):
        d = ctypes.windll.dxva2
        dw = wintypes.DWORD
        d.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, ctypes.POINTER(dw)]
        d.GetPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, dw, ctypes.POINTER(PHYSICAL_MONITOR)]
        d.GetMonitorBrightness.argtypes = [ctypes.c_void_p, ctypes.POINTER(dw), ctypes.POINTER(dw), ctypes.POINTER(dw)]
        d.SetMonitorBrightness.argtypes = [ctypes.c_void_p, dw]
        d.DestroyPhysicalMonitors.argtypes = [dw, ctypes.POINTER(PHYSICAL_MONITOR)]
        return d

    def dim(self):
        if self.mode:
            return
        if not self._dim_ddc():
            self._dim_wmi()

    def _dim_ddc(self):
        try:
            u, d = ctypes.windll.user32, self._dxva2()
            u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            u.MonitorFromWindow.restype = ctypes.c_void_p
            hmon = u.MonitorFromWindow(0, 1)  # primary monitor
            n = wintypes.DWORD()
            if not d.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value == 0:
                return False
            arr = (PHYSICAL_MONITOR * n.value)()
            if not d.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                return False
            saved = []
            for m in arr:
                lo, cur, hi = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                if d.GetMonitorBrightness(m.handle, ctypes.byref(lo), ctypes.byref(cur), ctypes.byref(hi)):
                    d.SetMonitorBrightness(m.handle, lo.value)
                    saved.append((m.handle, cur.value))
            if saved:
                self.mode, self.saved, self.monitors = "ddc", saved, arr
                return True
            d.DestroyPhysicalMonitors(n.value, arr)
        except Exception:
            log.exception("DDC/CI dimming failed")
        return False

    def _dim_wmi(self):
        try:
            current = int(run_powershell(WMI_GET).stdout.strip())
            if run_powershell(WMI_SET % 0).returncode != 0:
                return False
            self.mode, self.saved = "wmi", current
            return True
        except Exception:
            log.exception("WMI dimming failed")
            return False

    def restore(self):
        mode, self.mode = self.mode, None
        try:
            if mode == "ddc":
                d = self._dxva2()
                for handle, level in self.saved:
                    d.SetMonitorBrightness(handle, level)
                d.DestroyPhysicalMonitors(len(self.monitors), self.monitors)
            elif mode == "wmi":
                run_powershell(WMI_SET % int(self.saved))
        except Exception:
            log.exception("Restoring brightness failed")
