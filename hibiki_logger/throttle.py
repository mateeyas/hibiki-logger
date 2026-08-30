"""
Deduplication and rate limiting for Discord alerts.

Discord rate limits webhooks at roughly 5 requests per 2 seconds and
returns 429 beyond that. Without throttling, a crash loop or database
outage produces one alert per request, exceeds the limit, and loses
alerts silently, because send failures are logged rather than raised.
The alerting is then least reliable exactly when it is most needed.

Two mechanisms, in order:

1. Deduplication collapses alerts sharing a signature inside a window.
   This does nearly all the work: a crash loop repeats one signature.
2. A send budget backstops the rest, for the case dedup cannot catch --
   distinct messages arriving in bulk.

Alerts beyond the budget are dropped rather than queued, and the number
dropped is reported on the next send. Dropping is acceptable here because
Discord is the notification channel, not the record: every log record is
still written to the database by the DB handler. Queueing would buy
completeness this package does not need, at the cost of a background
worker and its lifecycle.

State is a dict and a list of timestamps, inspected synchronously. There
is no background task to start, drain, or shut down.
"""

import logging
import re
import time
from typing import Callable, Optional, Tuple

from .config import config as logging_config

logger = logging.getLogger("hibiki_logger.discord")

# Upper bound on tracked dedup signatures, so a pathological spread of
# distinct errors cannot grow the table without limit.
MAX_TRACKED_SIGNATURES = 512

_WINDOW_SECONDS = 60.0

# Final line of a traceback: "ExceptionType: message". The type alone is
# the stable part; the message often carries ids and varies per occurrence.
_EXC_LINE = re.compile(r"^([A-Za-z_][\w.]*)\s*:", re.MULTILINE)

# "  File "path", line N, in func"
_FRAME_LINE = re.compile(
    r'^\s+File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$', re.MULTILINE
)


class ThrottleDecision:
    """Outcome of a throttle check for one alert.

    A decision to send reserves a dedup window and a budget slot. If the
    send then fails, pass the decision to ``record_failure`` so the window
    is released; see that method for why the budget slot is not.
    """

    __slots__ = ("send", "suppressed", "dropped", "_key", "_previous_window")

    def __init__(self, send: bool, suppressed: int = 0, dropped: int = 0):
        self.send = send
        # Occurrences of this signature collapsed since it was last sent.
        self.suppressed = suppressed
        # Alerts discarded for exceeding the send budget since the last send.
        self.dropped = dropped
        self._key = None
        self._previous_window = None

    def __repr__(self) -> str:
        return (
            f"ThrottleDecision(send={self.send}, suppressed={self.suppressed}, "
            f"dropped={self.dropped})"
        )


class _Window:
    """One dedup signature: when its window opened, what it has absorbed."""

    __slots__ = ("opened_at", "suppressed")

    def __init__(self, opened_at: float):
        self.opened_at = opened_at
        self.suppressed = 0


def signature(
    level: str,
    message: str,
    logger_name: str,
    trace: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Derive the dedup signature for an alert.

    When a traceback is present, the exception type and the innermost
    frame identify the fault far better than the message does. Messages
    routinely embed request ids, user ids, and values, so keying on the
    message alone lets a single repeating fault present as thousands of
    distinct alerts -- the exact case throttling exists to contain.

    Falls back to the message when there is no usable traceback.
    """
    if trace:
        exc_types = _EXC_LINE.findall(trace)
        frames = _FRAME_LINE.findall(trace)
        if exc_types or frames:
            exc_type = exc_types[-1] if exc_types else "?"
            # Frames run outermost first, so the last is where it raised.
            innermost = "?"
            if frames:
                path, line_no, func = frames[-1]
                innermost = f"{path}:{line_no}:{func}"
            return (logger_name, (level or "").upper(), f"{exc_type}@{innermost}")

    return (logger_name, (level or "").upper(), message or "")


class DiscordThrottle:
    """Decides whether an alert should reach the webhook.

    ``check`` is safe to call from a logging handler: it touches no
    network, takes no locks, and never raises. It returns the counts the
    caller should surface in the message it sends.
    """

    def __init__(
        self,
        dedup_window: Optional[int] = None,
        max_per_minute: Optional[int] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._clock = clock
        self.dedup_window = (
            dedup_window
            if dedup_window is not None
            else logging_config.LOG_DISCORD_DEDUP_WINDOW
        )
        self.max_per_minute = max(
            1,
            max_per_minute
            if max_per_minute is not None
            else logging_config.LOG_DISCORD_MAX_PER_MINUTE,
        )

        self._windows: dict = {}
        self._sends: list = []
        self._dropped_pending = 0

    def check(
        self,
        level: str,
        message: str,
        logger_name: str,
        trace: Optional[str] = None,
    ) -> ThrottleDecision:
        """Decide whether to send this alert, and with what counts."""
        now = self._clock()
        key = signature(level, message, logger_name, trace)
        window = self._windows.get(key)

        if window is not None and now - window.opened_at < self.dedup_window:
            window.suppressed += 1
            return ThrottleDecision(False)

        # The window has expired, or this signature is new. Anything the
        # expired window absorbed is reported on this send.
        pending = window.suppressed if window is not None else 0

        if not self._has_budget(now):
            # Shed the alert but keep the window, so its suppression count
            # is not lost, and count the drop for the next successful send.
            self._dropped_pending += 1
            return ThrottleDecision(False)

        self._sweep(now)
        self._windows[key] = _Window(now)
        self._sends.append(now)

        dropped = self._dropped_pending
        self._dropped_pending = 0

        decision = ThrottleDecision(True, suppressed=pending, dropped=dropped)
        decision._key = key
        decision._previous_window = window
        return decision

    def record_failure(self, decision: ThrottleDecision) -> None:
        """Release the dedup window reserved by a send that did not land.

        Without this, a webhook that is briefly unreachable silences the
        fault for the whole dedup window: the first alert opens the window,
        fails to deliver, and every later occurrence is collapsed into an
        alert nobody received. That is the failure this module exists to
        prevent, so a failed send must not count as a send.

        The budget slot is deliberately *not* released. Retrying a fault
        whose webhook is down should stay bounded, and letting failures
        consume budget caps the attempts at LOG_DISCORD_MAX_PER_MINUTE
        rather than one per occurrence.
        """
        if not decision.send or decision._key is None:
            return

        # Occurrences that arrived while the send was in flight landed on
        # the window the send opened. They were neither delivered nor
        # reported, so they have to survive the rollback.
        in_flight = self._windows.get(decision._key)
        carried = in_flight.suppressed if in_flight is not None else 0

        if decision._previous_window is not None:
            decision._previous_window.suppressed += carried
            self._windows[decision._key] = decision._previous_window
        elif carried:
            # No earlier window to restore. Backdate this one so it counts
            # as expired and the next occurrence sends and reports them.
            in_flight.opened_at = self._clock() - self.dedup_window
        else:
            self._windows.pop(decision._key, None)

        # Counts were consumed by an alert that never arrived; report them
        # on whichever send lands next.
        self._dropped_pending += decision.dropped

    def _has_budget(self, now: float) -> bool:
        """True when a send now stays inside the sliding-window budget."""
        cutoff = now - _WINDOW_SECONDS
        # Sends are appended in order, so dropping the stale head suffices.
        # The list never exceeds the budget, so this stays cheap.
        while self._sends and self._sends[0] <= cutoff:
            self._sends.pop(0)
        return len(self._sends) < self.max_per_minute

    def _sweep(self, now: float) -> None:
        """Discard expired windows that have nothing left to report.

        Windows holding a suppression count are kept until that count is
        delivered. Beyond a hard cap the oldest are discarded regardless,
        so a pathological spread of distinct faults cannot grow the table
        without limit.
        """
        if len(self._windows) < MAX_TRACKED_SIGNATURES:
            expired = [
                key
                for key, window in self._windows.items()
                if window.suppressed == 0 and now - window.opened_at >= self.dedup_window
            ]
            for key in expired:
                del self._windows[key]
            return

        ordered = sorted(self._windows.items(), key=lambda item: item[1].opened_at)
        for key, _ in ordered[: len(self._windows) - MAX_TRACKED_SIGNATURES + 1]:
            del self._windows[key]

    def reset(self) -> None:
        """Clear all throttle state. Intended for use in tests."""
        self._windows.clear()
        self._sends.clear()
        self._dropped_pending = 0
