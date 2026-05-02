from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


IDLE_THRESHOLD_S = 30  # seconds of inactivity = chunk boundary


@dataclass
class RawEvent:
    source: str        # "agent" | "user"
    window: str        # active window title at time of event
    action: str        # brief description of what happened
    timestamp: float = field(default_factory=time.time)


@dataclass
class Chunk:
    window:    str
    source:    str
    actions:   list[str]
    started:   float
    ended:     float

    @property
    def duration_s(self) -> int:
        return int(self.ended - self.started)


class Aggregator:
    """
    Deterministic event chunker. No ML.

    Chunk boundaries:
    1. Window/tab change
    2. Idle gap > IDLE_THRESHOLD_S within same window
    3. Source change (user → agent or agent → user)

    When a chunk closes, calls on_chunk(chunk).
    """

    def __init__(self, on_chunk: Callable[[Chunk], None]):
        self._on_chunk   = on_chunk
        self._lock       = threading.Lock()
        self._current:   Chunk | None = None
        self._last_event_time: float = 0
        self._idle_timer: threading.Timer | None = None

    def push(self, event: RawEvent):
        with self._lock:
            self._cancel_idle_timer()

            if self._current is None:
                # Start first chunk
                self._current = Chunk(
                    window=event.window,
                    source=event.source,
                    actions=[event.action],
                    started=event.timestamp,
                    ended=event.timestamp,
                )
            else:
                boundary = self._is_boundary(event)
                if boundary:
                    self._close_current(event.timestamp)
                    self._current = Chunk(
                        window=event.window,
                        source=event.source,
                        actions=[event.action],
                        started=event.timestamp,
                        ended=event.timestamp,
                    )
                else:
                    self._current.actions.append(event.action)
                    self._current.ended = event.timestamp

            self._last_event_time = event.timestamp
            self._start_idle_timer()

    def flush(self):
        """Force-close the current chunk. Call on session end."""
        with self._lock:
            self._cancel_idle_timer()
            if self._current and self._current.actions:
                self._close_current(time.time())

    def _is_boundary(self, event: RawEvent) -> bool:
        if not self._current:
            return False
        if event.window != self._current.window:
            return True
        if event.source != self._current.source:
            return True
        return False

    def _close_current(self, ended: float):
        if self._current and self._current.actions:
            self._current.ended = ended
            self._on_chunk(self._current)
        self._current = None

    def _start_idle_timer(self):
        self._idle_timer = threading.Timer(
            IDLE_THRESHOLD_S,
            self._on_idle
        )
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self):
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _on_idle(self):
        with self._lock:
            if self._current and self._current.actions:
                self._close_current(time.time())
