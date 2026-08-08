"""
Rejects brief single-frame outlier spikes (a momentary detection glitch,
e.g. a blink or a landmark misdetection) by replacing each sample with the
median of the last `window` samples.

This is a different failure mode than steady jitter: a low-pass filter
(like the One Euro Filter) responds to any large frame-to-frame change as
if it were fast deliberate movement, so it actually smooths a spike
*less*, not more, and the cursor visibly jumps toward the spike before
decaying back. A median is robust to a single wild sample as long as most
of the window is normal, so it should be applied before further smoothing,
not instead of it.
"""

from collections import deque
import statistics


class MedianFilter:
    def __init__(self, window=3):
        self._buffer = deque(maxlen=window)

    def filter(self, value):
        self._buffer.append(value)
        return statistics.median(self._buffer)
