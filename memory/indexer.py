from __future__ import annotations
import json
import re
import threading
from queue import Queue, Empty
from memory.aggregator import Chunk
from memory.store import store


# Small fast model — 8b is enough for summarization
INDEXER_MODEL = "llama-3.1-8b-instant"


class Indexer:
    """
    Consumes chunks from the Aggregator queue.
    For each chunk:
      1. Calls small LLM to produce a summary + tags
      2. Updates mandatory context (4-5 fields)
      3. Writes index entry to store
    Runs in a background thread — never blocks the shell.
    """

    def __init__(self, groq_api_key: str):
        self._api_key = groq_api_key
        self._queue:  Queue[Chunk] = Queue()
        self._thread  = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, chunk: Chunk):
        self._queue.put(chunk)

    def _worker(self):
        while True:
            try:
                chunk = self._queue.get(timeout=1)
                self._process(chunk)
                self._queue.task_done()
            except Empty:
                continue
            except Exception as e:
                print(f"[Indexer] ⚠️ Worker error: {e}")

    def _process(self, chunk: Chunk):
        current_ctx = store.get_context()
        prompt = _build_prompt(chunk, current_ctx)

        try:
            result = _call_llm(prompt, self._api_key)
            index_entry = result.get("index_entry", {})
            new_ctx     = result.get("mandatory_context", {})

            if index_entry.get("summary"):
                store.add_chunk(
                    window=chunk.window,
                    summary=index_entry["summary"],
                    tags=index_entry.get("tags", []),
                    source=chunk.source,
                )

            if new_ctx:
                store.set_context(new_ctx)

        except Exception as e:
            # Fallback: store chunk as-is without LLM
            print(f"[Indexer] ⚠️ LLM failed, storing raw chunk: {e}")
            store.add_chunk(
                window=chunk.window,
                summary=f"{chunk.source}: {'; '.join(chunk.actions[:3])}",
                tags=[chunk.source, chunk.window.split()[0].lower()],
                source=chunk.source,
            )


def _build_prompt(chunk: Chunk, current_ctx: dict) -> str:
    actions_str = "\n".join(f"  - {a}" for a in chunk.actions)
    ctx_str = json.dumps(current_ctx, ensure_ascii=False) if current_ctx else "{}"

    return f"""You process activity chunks into structured memory for an AI agent.

CHUNK:
- window: {chunk.window}
- source: {chunk.source}  (agent = AI did this, user = human did this)
- duration: {chunk.duration_s}s
- actions:
{actions_str}

CURRENT CONTEXT:
{ctx_str}

Produce a JSON object with exactly two keys:

"index_entry": {{
  "summary": "One sentence. What happened and why it matters.",
  "tags": ["2-4 lowercase tags relevant to the activity"]
}}

"mandatory_context": {{
  "active_window": "current window title",
  "last_action": "most recent action in one short phrase",
  "result": "what changed or what is now true",
  "state": "what the agent/user is doing now: reading | writing | navigating | idle | executing | waiting",
  "session_goal": "inferred overall goal of this session, or null if unclear"
}}

Rules:
- mandatory_context must have exactly these 5 fields, no more
- session_goal should persist if already set and still relevant
- Be factual, not speculative
- Return ONLY the JSON object, no markdown, no explanation
"""


def _call_llm(prompt: str, api_key: str) -> dict:
    from groq import Groq
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=INDEXER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=512,
    )
    raw = response.choices[0].message.content or ""
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    return json.loads(raw)
