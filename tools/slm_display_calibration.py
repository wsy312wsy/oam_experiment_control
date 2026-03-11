from __future__ import annotations

import argparse
import ctypes
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.slm_display_mapping import (  # noqa: E402
    DEFAULT_MAPPING_PATH,
    load_slm_display_mapping,
    save_slm_display_mapping,
)


@dataclass(frozen=True)
class MonitorInfo:
    monitor_id: str
    x: int
    y: int
    width: int
    height: int
    is_primary: bool
    device_name: str


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def enumerate_monitors() -> List[MonitorInfo]:
    user32 = ctypes.windll.user32
    monitors: List[MonitorInfo] = []

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        ctypes.c_long,
    )

    def _callback(hmonitor, _hdc, _rect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        ok = user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        if ok:
            rect = info.rcMonitor
            monitor_id = info.szDevice.replace("\\\\.\\", "")
            monitors.append(
                MonitorInfo(
                    monitor_id=monitor_id,
                    x=int(rect.left),
                    y=int(rect.top),
                    width=int(rect.right - rect.left),
                    height=int(rect.bottom - rect.top),
                    is_primary=bool(info.dwFlags & 1),
                    device_name=info.szDevice,
                )
            )
        return 1

    cb_func = monitor_enum_proc(_callback)
    if not user32.EnumDisplayMonitors(0, 0, cb_func, 0):
        raise RuntimeError("EnumDisplayMonitors failed")

    monitors.sort(key=lambda m: (m.x, m.y, m.monitor_id))
    return monitors


def print_monitor_summary(monitors: List[MonitorInfo]) -> None:
    print("\nDetected monitors:")
    print(
        f"{'monitor_id':<16} {'resolution':<14} {'position':<14} {'primary':<8} {'device_name'}"
    )
    for monitor in monitors:
        print(
            f"{monitor.monitor_id:<16} "
            f"{monitor.width}x{monitor.height:<8} "
            f"({monitor.x},{monitor.y})".ljust(14)
            + " "
            + f"{str(monitor.is_primary):<8} "
            + f"{monitor.device_name}"
        )


class PatternDisplaySession:
    def __init__(self, assignments: List[Tuple[MonitorInfo, str, str]]) -> None:
        self.assignments = assignments
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        started = self._started.wait(timeout=5.0)
        if not started:
            raise RuntimeError("Failed to start test pattern window thread")
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            windows: List[tk.Toplevel] = []

            for monitor, label, bg_color in self.assignments:
                win = tk.Toplevel(root)
                win.overrideredirect(True)
                win.attributes("-topmost", True)
                win.geometry(f"{monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}")

                canvas = tk.Canvas(win, bg=bg_color, highlightthickness=0)
                canvas.pack(fill="both", expand=True)

                margin = max(12, min(monitor.width, monitor.height) // 20)
                canvas.create_rectangle(
                    margin,
                    margin,
                    monitor.width - margin,
                    monitor.height - margin,
                    outline="white",
                    width=max(4, margin // 3),
                )
                canvas.create_line(
                    monitor.width // 2,
                    margin,
                    monitor.width // 2,
                    monitor.height - margin,
                    fill="white",
                    width=max(3, margin // 4),
                )
                canvas.create_line(
                    margin,
                    monitor.height // 2,
                    monitor.width - margin,
                    monitor.height // 2,
                    fill="white",
                    width=max(3, margin // 4),
                )

                font_size = max(48, min(monitor.width, monitor.height) // 8)
                canvas.create_text(
                    monitor.width // 2,
                    monitor.height // 2,
                    text=f"{label}\n{monitor.monitor_id}",
                    fill="white",
                    font=("Arial", font_size, "bold"),
                    justify="center",
                )
                windows.append(win)

            self._started.set()

            def _poll_stop() -> None:
                if self._stop_event.is_set():
                    root.quit()
                    return
                root.after(100, _poll_stop)

            root.after(100, _poll_stop)
            root.mainloop()

            for win in windows:
                try:
                    win.destroy()
                except Exception:
                    pass
            root.destroy()
        except Exception as exc:
            self._error = exc
            self._started.set()


def _prompt_monitor_id(prompt: str, valid_ids: List[str], disallow: str | None = None) -> str:
    while True:
        value = input(prompt).strip()
        if value not in valid_ids:
            print(f"Invalid monitor_id: {value}. Valid options: {', '.join(valid_ids)}")
            continue
        if disallow is not None and value == disallow:
            print("SLM1 and SLM2 monitor_id must be different.")
            continue
        return value


def _choose_candidate_ids(monitors: List[MonitorInfo]) -> Tuple[str, str]:
    valid_ids = [m.monitor_id for m in monitors]
    extended = [m.monitor_id for m in monitors if not m.is_primary]
    if len(extended) >= 2:
        return extended[0], extended[1]

    print(
        "\nLess than two non-primary monitors were detected. "
        "Please manually choose two monitors for test-pattern display."
    )
    id1 = _prompt_monitor_id("Candidate monitor A id: ", valid_ids)
    id2 = _prompt_monitor_id("Candidate monitor B id: ", valid_ids, disallow=id1)
    return id1, id2


def _monitor_summary_payload(monitors: List[MonitorInfo]) -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for m in monitors:
        payload.append(
            {
                "monitor_id": m.monitor_id,
                "resolution": f"{m.width}x{m.height}",
                "position": {"x": m.x, "y": m.y},
                "is_primary": m.is_primary,
                "device_name": m.device_name,
            }
        )
    return payload


def run_calibration(mapping_path: Path) -> int:
    monitors = enumerate_monitors()
    if len(monitors) < 2:
        print("At least two monitors are required for dual-SLM calibration.")
        return 1
    print_monitor_summary(monitors)

    id_a, id_b = _choose_candidate_ids(monitors)
    monitor_by_id = {m.monitor_id: m for m in monitors}
    assignments = [
        (monitor_by_id[id_a], "SLM1_TEST", "#ad0000"),
        (monitor_by_id[id_b], "SLM2_TEST", "#005f8f"),
    ]

    print(
        "\nShowing test patterns now."
        "\nObserve both SLM screens, then return here and press Enter to continue input..."
    )
    session = PatternDisplaySession(assignments)
    session.start()
    try:
        input()
    finally:
        session.stop()
        time.sleep(0.15)

    valid_ids = [m.monitor_id for m in monitors]
    print("\nEnter final binding based on your observation:")
    slm1_monitor_id = _prompt_monitor_id("monitor_id for SLM1: ", valid_ids)
    slm2_monitor_id = _prompt_monitor_id(
        "monitor_id for SLM2: ",
        valid_ids,
        disallow=slm1_monitor_id,
    )
    saved_path = save_slm_display_mapping(
        slm1_monitor_id=slm1_monitor_id,
        slm2_monitor_id=slm2_monitor_id,
        monitor_summary=_monitor_summary_payload(monitors),
        mapping_path=mapping_path,
    )
    print(f"\nCalibration saved: {saved_path}")
    return 0


def run_verify(mapping_path: Path) -> int:
    mapping = load_slm_display_mapping(mapping_path)
    monitors = enumerate_monitors()
    print_monitor_summary(monitors)
    monitor_by_id = {m.monitor_id: m for m in monitors}
    if mapping.slm1_monitor_id not in monitor_by_id or mapping.slm2_monitor_id not in monitor_by_id:
        print(
            "\nSaved mapping does not match current monitor ids."
            f"\nExpected SLM1={mapping.slm1_monitor_id}, SLM2={mapping.slm2_monitor_id}"
        )
        return 1

    assignments = [
        (monitor_by_id[mapping.slm1_monitor_id], "SLM1_VERIFY", "#4b006e"),
        (monitor_by_id[mapping.slm2_monitor_id], "SLM2_VERIFY", "#0a6e00"),
    ]
    print(
        "\nVerify mode: showing mapping-based test patterns."
        "\nObserve SLM1/SLM2 screens, then press Enter here to close."
    )
    session = PatternDisplaySession(assignments)
    session.start()
    try:
        input()
    finally:
        session.stop()
        time.sleep(0.15)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dual-SLM display binding calibration tool")
    parser.add_argument(
        "--mapping-path",
        default=str(DEFAULT_MAPPING_PATH),
        help="Output/input mapping yaml path. Default: config/slm_display_mapping.yaml",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read existing mapping and display verify patterns on mapped monitors",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping_path = Path(args.mapping_path)
    if args.verify:
        return run_verify(mapping_path)
    return run_calibration(mapping_path)


if __name__ == "__main__":
    raise SystemExit(main())

