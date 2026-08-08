"""
One Euro Filter (Casiez, Roussel, Vogel, CHI 2012): an adaptive low-pass
filter designed specifically for noisy pointing/gaze signals. It smooths
heavily when the signal is nearly still (killing jitter at rest) and
smooths less as the signal speeds up (avoiding lag while moving), instead
of trading one off against the other with a single fixed smoothing amount.

min_cutoff: baseline cutoff frequency. Lower = more smoothing at rest.
beta: how much cutoff increases with speed. Higher = less lag when moving
      fast, at the cost of a bit more jitter while moving.
"""

import math


class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _smoothing_factor(dt, cutoff):
        r = 2 * math.pi * cutoff * dt
        return r / (r + 1)

    @staticmethod
    def _exponential_smoothing(alpha, x, x_prev):
        return alpha * x + (1 - alpha) * x_prev

    def filter(self, x, timestamp):
        if self._t_prev is None:
            self._t_prev = timestamp
            self._x_prev = x
            self._dx_prev = 0.0
            return x

        dt = max(timestamp - self._t_prev, 1e-6)

        # filter the derivative (speed) first
        dx = (x - self._x_prev) / dt
        a_d = self._smoothing_factor(dt, self.d_cutoff)
        dx_hat = self._exponential_smoothing(a_d, dx, self._dx_prev)

        # use the filtered speed to adapt the cutoff for the value itself
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._smoothing_factor(dt, cutoff)
        x_hat = self._exponential_smoothing(a, x, self._x_prev)

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = timestamp
        return x_hat
