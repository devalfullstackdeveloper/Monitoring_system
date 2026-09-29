"""
Detects automated / mechanical mouse movement such as USB mouse jigglers.

The detector groups mouse moves into bursts and looks for repeated bursts with
nearly identical start intervals and durations. Clicks, scrolls, and key
events mark the current burst as genuine activity.
"""

import statistics
import time
from collections import deque


class MousePatternDetector:
    def __init__(
        self,
        burst_gap_seconds=1.5,
        min_cycles_to_flag=4,
        interval_cv_threshold=0.08,
        burst_duration_cv_threshold=0.25,
        burst_history_size=12,
        max_burst_duration_seconds=3.0,
    ):
        self.burst_gap_seconds = burst_gap_seconds
        self.min_cycles_to_flag = min_cycles_to_flag
        self.interval_cv_threshold = interval_cv_threshold
        self.burst_duration_cv_threshold = burst_duration_cv_threshold
        self.max_burst_duration_seconds = max_burst_duration_seconds
        self._bursts = deque(maxlen=burst_history_size)
        self.reset()

    def reset(self):
        self._bursts.clear()
        self._current_burst_start = None
        self._current_burst_last_move = None
        self._current_burst_had_input = False

    def record_mouse_move(self, timestamp=None):
        """Call on every raw mouse-move event."""
        now = timestamp if timestamp is not None else time.monotonic()
        if (
            self._current_burst_start is None
            or now - self._current_burst_last_move > self.burst_gap_seconds
        ):
            self._close_current_burst()
            self._current_burst_start = now
            self._current_burst_had_input = False
        self._current_burst_last_move = now

    def record_other_input(self, timestamp=None):
        """Mark the current mouse burst as genuine human activity."""
        self._current_burst_had_input = True

    def _close_current_burst(self):
        if self._current_burst_start is None:
            return
        duration = self._current_burst_last_move - self._current_burst_start
        self._bursts.append(
            {
                "start": self._current_burst_start,
                "duration": duration,
                "had_input": self._current_burst_had_input,
            }
        )
        self._current_burst_start = None
        self._current_burst_last_move = None
        self._current_burst_had_input = False

    def is_automated_pattern(self, now=None):
        """Return whether recent mouse bursts look mechanical."""
        check_time = now if now is not None else time.monotonic()
        if (
            self._current_burst_last_move is not None
            and check_time - self._current_burst_last_move > self.burst_gap_seconds
        ):
            return False

        bursts = list(self._bursts)
        if self._current_burst_start is not None:
            bursts.append(
                {
                    "start": self._current_burst_start,
                    "duration": self._current_burst_last_move
                    - self._current_burst_start,
                    "had_input": self._current_burst_had_input,
                }
            )

        if len(bursts) < self.min_cycles_to_flag + 1:
            return False

        recent = bursts[-(self.min_cycles_to_flag + 1):]
        if any(burst["had_input"] for burst in recent):
            return False
        if any(
            burst["duration"] > self.max_burst_duration_seconds
            for burst in recent
        ):
            return False

        intervals = [
            recent[index + 1]["start"] - recent[index]["start"]
            for index in range(len(recent) - 1)
        ]
        durations = [burst["duration"] for burst in recent]
        return (
            self._is_regular(intervals, self.interval_cv_threshold)
            and self._is_regular(durations, self.burst_duration_cv_threshold)
        )

    @staticmethod
    def _is_regular(values, cv_threshold):
        if len(values) < 2:
            return False
        mean = statistics.mean(values)
        if mean <= 0:
            return False
        return statistics.pstdev(values) / mean <= cv_threshold