from __future__ import annotations
from memory.aggregator import Aggregator, RawEvent
from memory.indexer import Indexer


class MemorySession:
    """
    Wires Aggregator → Indexer → Store.
    One instance per shell session.
    """

    def __init__(self, groq_api_key: str):
        self._indexer    = Indexer(groq_api_key)
        self._aggregator = Aggregator(on_chunk=self._indexer.enqueue)

    def record(self, window: str, action: str, source: str = "agent"):
        """Record an event. Call this after every command execution."""
        self._aggregator.push(RawEvent(
            source=source,
            window=window,
            action=action,
        ))

    def flush(self):
        """Close current chunk. Call on session end."""
        self._aggregator.flush()
