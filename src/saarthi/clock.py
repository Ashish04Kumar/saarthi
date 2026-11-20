"""Saarthi's clock for every "how long has it been" (sessions, cool-downs, animations).

`time.monotonic()` stops while the laptop sleeps (lid closed) on Linux and macOS, so a 60-minute lunch
started before closing the lid would still have its minutes left after two hours of sleep. This clock
keeps counting through sleep:

* Linux: CLOCK_BOOTTIME (monotonic, includes suspend)
* macOS: CLOCK_MONOTONIC (on macOS it keeps counting while asleep, unlike time.monotonic)
* elsewhere (Windows): the wall clock, which also keeps going through sleep

Always use clock.now() instead of time.monotonic() so all timestamps share one time base.
"""

from __future__ import annotations

import sys
import time

if sys.platform.startswith("linux") and hasattr(time, "CLOCK_BOOTTIME"):

    def now() -> float:
        return time.clock_gettime(time.CLOCK_BOOTTIME)

elif sys.platform == "darwin" and hasattr(time, "CLOCK_MONOTONIC"):

    def now() -> float:
        return time.clock_gettime(time.CLOCK_MONOTONIC)

else:

    def now() -> float:
        return time.time()
