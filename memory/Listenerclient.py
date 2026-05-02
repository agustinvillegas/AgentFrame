from __future__ import annotations
import json
import threading
import time
from memory.aggregator import Aggregator, RawEvent


PIPE_NAME = r"\\.\pipe\agentshell_listener"
RECONNECT_DELAY_S = 3


class ListenerClient:
    """
    Reads JSON events from the C# Listener via named pipe.
    Converts them to RawEvents and pushes to the Aggregator.
    Runs in a background thread — reconnects automatically if pipe drops.
    """

    def __init__(self, aggregator: Aggregator):
        self._aggregator = aggregator
        self._running    = False
        self._thread     = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._running = True
        self._thread.start()
        print("[Listener] Client started — connecting to pipe...")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._connect_and_read()
            except Exception as e:
                print(f"[Listener] Disconnected ({e}). Retrying in {RECONNECT_DELAY_S}s...")
                time.sleep(RECONNECT_DELAY_S)

    def _connect_and_read(self):
        import win32pipe, win32file, pywintypes  # type: ignore

        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_READ,
            0, None,
            win32file.OPEN_EXISTING,
            0, None
        )

        print("[Listener] Connected to C# listener.")
        buffer = ""

        try:
            while self._running:
                try:
                    _, data = win32file.ReadFile(handle, 4096)
                    buffer += data.decode("utf-8", errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_event(line)

                except Exception:
                    break
        finally:
            win32file.CloseHandle(handle)
            print("[Listener] Pipe handle closed.")

    def _handle_event(self, line: str):
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            return

        event_type = evt.get("type", "")
        window     = evt.get("window") or evt.get("name") or "unknown"
        ts         = evt.get("ts", time.time())

        action = _describe(evt)
        if not action:
            return

        raw = RawEvent(
            source="user",
            window=window,
            action=action,
            timestamp=float(ts),
        )
        self._aggregator.push(raw)


def _describe(evt: dict) -> str | None:
    """Convert a raw event dict to a human-readable action string."""
    t = evt.get("type", "")

    if t == "window_change":
        return f"switched to window: {evt.get('window', '')}"

    if t == "tab_change":
        return f"navigated to tab: {evt.get('window', '')}"

    if t == "process_start":
        return f"launched process: {evt.get('name', '')}"

    if t == "process_stop":
        # Ignore noisy background processes
        name = evt.get("name", "").lower()
        NOISY = {"conhost.exe", "svchost.exe", "runtimebroker.exe",
                 "searchhost.exe", "wermgr.exe", "backgroundtaskhost.exe"}
        if name in NOISY:
            return None
        return f"process stopped: {evt.get('name', '')}"

    if t == "keystroke_burst":
        count = evt.get("char_count", 0)
        return f"typed {count} characters in: {evt.get('window', '')}"

    if t == "click":
        return f"clicked at ({evt.get('x')}, {evt.get('y')}) in: {evt.get('window', '')}"

    return None