from __future__ import annotations
from memory.aggregator import Aggregator, RawEvent
from memory.indexer import Indexer


class MemorySession:
    def __init__(self, groq_api_key: str):
        self._indexer    = Indexer(groq_api_key)
        self._aggregator = Aggregator(on_chunk=self._indexer.enqueue)

    def record(self, window: str, action: str, source: str = "agent"):
        self._aggregator.push(RawEvent(
            source=source,
            window=window,
            action=action,
        ))

    def flush(self):
        self._aggregator.flush()

