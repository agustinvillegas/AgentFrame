from __future__ import annotations
import json
import re
import threading
from queue import Queue, Empty
from memory.aggregator import Chunk
from memory.store import store

INDEXER_MODEL = "llama-3.1-8b-instant"

# Agent command actions that are fully deterministic — no LLM needed
_SIMPLE_AGENT_ACTIONS = {
    "audio volume", "audio mute", "mouse click", "mouse move",
    "mouse scroll", "mouse drag", "keyboard press", "keyboard hotkey",
    "window minimize", "window focus", "window close", "app launch",
    "app close", "files delete", "files move", "files copy",
}

# Tags derived deterministically from action names
_ACTION_TAGS: dict[str, list[str]] = {
    "audio":    ["audio", "system"],
    "mouse":    ["mouse", "interaction"],
    "keyboard": ["keyboard", "input"],
    "window":   ["window", "navigation"],
    "app":      ["app", "system"],
    "files":    ["files", "filesystem"],
    "screen":   ["screen", "perception"],
    "index":    ["memory", "context"],
    "context":  ["memory", "context"],
}


def _is_simple_chunk(chunk: Chunk) -> bool:
    """
    A chunk is simple if:
    - Source is 'agent' (not user)
    - All actions are single known commands
    - No user-generated text (typing, searches)
    """
    if chunk.source != "agent":
        return False
    for action in chunk.actions:
        parts = action.strip().lower().split()
        key = " ".join(parts[:2]) if len(parts) >= 2 else action
        if key not in _SIMPLE_AGENT_ACTIONS:
            return False
    return True


def _process_simple(chunk: Chunk) -> tuple[dict, dict]:
    """
    Deterministically build index_entry + context for simple agent chunks.
    Zero LLM calls.
    """
    actions = chunk.actions
    last    = actions[-1] if actions else "unknown"
    group   = last.split()[0].lower() if actions else "agent"

    summary = f"Agent executed {len(actions)} command(s): {'; '.join(actions[:3])}"
    if len(actions) > 3:
        summary += f" (+{len(actions) - 3} more)"

    tags = _ACTION_TAGS.get(group, ["agent"]) + ["agent"]

    index_entry = {"summary": summary, "tags": list(set(tags))}

    # Context: update only what we know for sure
    current_ctx = store.get_context()
    new_ctx = dict(current_ctx)
    new_ctx["active_window"] = chunk.window
    new_ctx["last_action"]   = last
    new_ctx["result"]        = "command executed"
    new_ctx["state"]         = "executing"
    # Preserve session_goal — don't overwrite with null

    return index_entry, new_ctx


def _process_with_llm(chunk: Chunk, api_key: str) -> tuple[dict, dict]:
    """Call Groq 8b for complex chunks (user activity, typing, navigation)."""
    current_ctx = store.get_context()
    prompt      = _build_prompt(chunk, current_ctx)
    result      = _call_llm(prompt, api_key)
    return result.get("index_entry", {}), result.get("mandatory_context", {})


class Indexer:
    """
    Consumes chunks from the Aggregator queue in a background thread.

    Routing:
    - Simple agent chunks  → deterministic processing (zero LLM calls)
    - Complex/user chunks  → Groq llama-3.1-8b-instant

    Never blocks the shell.
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
        try:
            if _is_simple_chunk(chunk):
                index_entry, new_ctx = _process_simple(chunk)
            else:
                index_entry, new_ctx = _process_with_llm(chunk, self._api_key)

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
            print(f"[Indexer] ⚠️ Processing failed, storing raw: {e}")
            store.add_chunk(
                window=chunk.window,
                summary=f"{chunk.source}: {'; '.join(chunk.actions[:3])}",
                tags=[chunk.source, chunk.window.split()[0].lower()],
                source=chunk.source,
            )


def _build_prompt(chunk: Chunk, current_ctx: dict) -> str:
    actions_str = "\n".join(f"  - {a}" for a in chunk.actions)
    ctx_str     = json.dumps(current_ctx, ensure_ascii=False) if current_ctx else "{}"

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
  "state": "reading | writing | navigating | idle | executing | waiting",
  "session_goal": "inferred overall goal of this session, or null if unclear"
}}

Rules:
- mandatory_context must have exactly these 5 fields, no more
- Preserve session_goal if already set and still relevant
- Be factual, not speculative
- Return ONLY the JSON object, no markdown, no explanation
"""


def _call_llm(prompt: str, api_key: str) -> dict:
    from groq import Groq
    client   = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=INDEXER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=512,
    )
    raw = response.choices[0].message.content or ""
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    return json.loads(raw)