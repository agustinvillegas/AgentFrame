from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import socket

class AgentShellClient:
    """
    Minimal Python client for AgentShell.
    Spawns the shell as a subprocess and communicates via stdin/stdout.
    """

    def __init__(self, shell_path: str | Path | None = None):
        self._shell_path = Path(shell_path) if shell_path else Path(__file__).parent.parent / "main.py"
        self._proc: subprocess.Popen | None = None
        self._start()

    def _start(self):
        self._proc = subprocess.Popen(
            [sys.executable, str(self._shell_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # capturar stderr separado
            text=True,
            bufsize=1,
        )
        import time
        time.sleep(2.0)  # esperar inicialización completa

    def run(self, command: str) -> dict:
        if not self._proc or self._proc.poll() is not None:
            self._start()

        try:
            self._proc.stdin.write(command + "\n")
            self._proc.stdin.flush()
        
            # Leer hasta encontrar una línea JSON válida
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    return {"ok": False, "error": "Shell process died"}
                line = line.strip()
                if not line:
                    continue
                if line.startswith("{"):
                    return json.loads(line)
            # Línea no JSON (logs del listener, etc.) — ignorar
        except Exception as e:
            return {"ok": False, "error": f"Client error: {e}"}

    def schema(self) -> dict:
        """Return the full command schema."""
        result = self.run("help --json")
        return result.get("data", {})

    def context(self) -> dict:
        """Return current mandatory context."""
        result = self.run("context get")
        return result.get("data", {}).get("context", {})

    def close(self):
        if self._proc:
            try:
                self._proc.stdin.write("exit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()