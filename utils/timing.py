from __future__ import annotations

import time


def sleep_seconds(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def elapsed_ms(start_perf: float) -> float:
    return (time.perf_counter() - start_perf) * 1000.0
