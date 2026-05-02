from __future__ import annotations
import os
import shutil
from pathlib import Path
from core.response import AgentResponse
from core.registry import registry, CommandParam

_MAX_READ_BYTES = 100_000  # 100KB cap — prevents dumping huge files into context


@registry.register(
    group="files",
    name="read",
    description="Read the contents of a file. Capped at 100KB — use offset/limit for large files.",
    params=[
        CommandParam("path",   "string", True,  None, "Absolute or relative file path"),
        CommandParam("offset", "int",    False, 0,    "Start reading from this line (0-indexed)"),
        CommandParam("limit",  "int",    False, None, "Max number of lines to return. Omit for full file."),
    ]
)
def read(path: str, offset: int = 0, limit: int | None = None) -> AgentResponse:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return AgentResponse.failure(f"File not found: {path}")
        if not p.is_file():
            return AgentResponse.failure(f"Not a file: {path}")

        size = p.stat().st_size
        raw  = p.read_bytes()[:_MAX_READ_BYTES]

        try:
            text  = raw.decode("utf-8")
        except UnicodeDecodeError:
            text  = raw.decode("latin-1", errors="replace")

        lines = text.splitlines()
        total = len(lines)

        if offset:
            lines = lines[offset:]
        if limit is not None:
            lines = lines[:limit]

        truncated = size > _MAX_READ_BYTES

        return AgentResponse.success({
            "content":   "\n".join(lines),
            "lines":     len(lines),
            "total_lines": total,
            "size_bytes": size,
            "truncated": truncated,
            "encoding":  "utf-8",
        })
    except PermissionError:
        return AgentResponse.failure(f"Permission denied: {path}")
    except Exception as e:
        return AgentResponse.failure(f"Read failed: {e}")


@registry.register(
    group="files",
    name="write",
    description="Write content to a file. Creates file and parent dirs if they don't exist.",
    params=[
        CommandParam("path",    "string", True,  None,    "Absolute or relative file path"),
        CommandParam("content", "string", True,  None,    "Content to write"),
        CommandParam("mode",    "string", False, "write", "'write' (overwrite) or 'append'"),
    ]
)
def write(path: str, content: str, mode: str = "write") -> AgentResponse:
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            p.write_text(content, encoding="utf-8")

        return AgentResponse.success(
            {
                "path":       str(p),
                "bytes":      len(content.encode("utf-8")),
                "mode":       mode,
            },
            state_delta={"last_action": f"wrote {p.name}", "result": f"file saved at {p}"}
        )
    except PermissionError:
        return AgentResponse.failure(f"Permission denied: {path}")
    except Exception as e:
        return AgentResponse.failure(f"Write failed: {e}")


@registry.register(
    group="files",
    name="list",
    description="List files and directories at a path.",
    params=[
        CommandParam("path",      "string", False, ".",    "Directory to list. Defaults to current dir."),
        CommandParam("filter",    "string", False, None,   "Glob pattern to filter. Example: '*.py', '*.txt'"),
        CommandParam("recursive", "bool",   False, False,  "List recursively if true"),
        CommandParam("dirs_only", "bool",   False, False,  "Only show directories"),
    ]
)
def list_files(
    path: str = ".",
    filter: str | None = None,
    recursive: bool = False,
    dirs_only: bool = False,
) -> AgentResponse:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return AgentResponse.failure(f"Path not found: {path}")
        if not p.is_dir():
            return AgentResponse.failure(f"Not a directory: {path}")

        pattern = filter or "*"
        if recursive:
            entries_raw = list(p.rglob(pattern))
        else:
            entries_raw = list(p.glob(pattern))

        entries = []
        for e in sorted(entries_raw):
            if dirs_only and not e.is_dir():
                continue
            try:
                stat = e.stat()
                entries.append({
                    "name":         e.name,
                    "path":         str(e),
                    "type":         "dir" if e.is_dir() else "file",
                    "size_bytes":   stat.st_size if e.is_file() else None,
                    "modified":     stat.st_mtime,
                })
            except Exception:
                continue

        return AgentResponse.success({
            "entries": entries,
            "count":   len(entries),
            "path":    str(p),
        })
    except PermissionError:
        return AgentResponse.failure(f"Permission denied: {path}")
    except Exception as e:
        return AgentResponse.failure(f"List failed: {e}")


@registry.register(
    group="files",
    name="search",
    description="Search for files by name or content. Name search is fast; content search reads files.",
    params=[
        CommandParam("query",   "string", True,  None,   "Text to search for"),
        CommandParam("path",    "string", False, ".",    "Root directory to search from"),
        CommandParam("mode",    "string", False, "name", "'name' (filename match) or 'content' (inside files)"),
        CommandParam("filter",  "string", False, None,   "Glob pattern to limit files searched. Example: '*.py'"),
        CommandParam("max",     "int",    False, 50,     "Max results to return"),
    ]
)
def search(
    query: str,
    path: str = ".",
    mode: str = "name",
    filter: str | None = None,
    max: int = 50,
) -> AgentResponse:
    try:
        root    = Path(path).expanduser().resolve()
        pattern = filter or "*"
        results = []
        query_l = query.lower()

        for entry in root.rglob(pattern):
            if len(results) >= max:
                break
            try:
                if mode == "name":
                    if query_l in entry.name.lower():
                        results.append({"path": str(entry), "type": "dir" if entry.is_dir() else "file"})
                elif mode == "content" and entry.is_file():
                    raw = entry.read_bytes()[:_MAX_READ_BYTES]
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if query_l in text.lower():
                        # Find first matching line for context
                        for i, line in enumerate(text.splitlines()):
                            if query_l in line.lower():
                                results.append({
                                    "path":    str(entry),
                                    "line":    i + 1,
                                    "preview": line.strip()[:120],
                                })
                                break
            except (PermissionError, OSError):
                continue

        return AgentResponse.success({
            "results": results,
            "count":   len(results),
            "query":   query,
            "mode":    mode,
            "capped":  len(results) >= max,
        })
    except Exception as e:
        return AgentResponse.failure(f"Search failed: {e}")


@registry.register(
    group="files",
    name="delete",
    description="Delete a file or empty directory.",
    params=[
        CommandParam("path",  "string", True,  None,  "File or directory path to delete"),
        CommandParam("force", "bool",   False, False, "If true, delete non-empty directories recursively"),
    ]
)
def delete(path: str, force: bool = False) -> AgentResponse:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return AgentResponse.failure(f"Path not found: {path}")

        if p.is_file():
            p.unlink()
        elif p.is_dir():
            if force:
                shutil.rmtree(p)
            else:
                p.rmdir()  # fails if not empty — intentional
        else:
            return AgentResponse.failure(f"Unsupported path type: {path}")

        return AgentResponse.success(
            {"deleted": str(p)},
            state_delta={"last_action": f"deleted {p.name}", "result": "file deleted"}
        )
    except OSError as e:
        return AgentResponse.failure(f"Delete failed (directory may not be empty — use --force): {e}")
    except Exception as e:
        return AgentResponse.failure(f"Delete failed: {e}")


@registry.register(
    group="files",
    name="move",
    description="Move or rename a file or directory.",
    params=[
        CommandParam("src",  "string", True, None, "Source path"),
        CommandParam("dst",  "string", True, None, "Destination path"),
    ]
)
def move(src: str, dst: str) -> AgentResponse:
    try:
        s = Path(src).expanduser().resolve()
        d = Path(dst).expanduser().resolve()
        if not s.exists():
            return AgentResponse.failure(f"Source not found: {src}")
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return AgentResponse.success(
            {"from": str(s), "to": str(d)},
            state_delta={"last_action": f"moved {s.name} to {d}", "result": "file moved"}
        )
    except PermissionError:
        return AgentResponse.failure(f"Permission denied")
    except Exception as e:
        return AgentResponse.failure(f"Move failed: {e}")


@registry.register(
    group="files",
    name="copy",
    description="Copy a file or directory.",
    params=[
        CommandParam("src",  "string", True, None, "Source path"),
        CommandParam("dst",  "string", True, None, "Destination path"),
    ]
)
def copy(src: str, dst: str) -> AgentResponse:
    try:
        s = Path(src).expanduser().resolve()
        d = Path(dst).expanduser().resolve()
        if not s.exists():
            return AgentResponse.failure(f"Source not found: {src}")
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            shutil.copy2(str(s), str(d))
        return AgentResponse.success(
            {"from": str(s), "to": str(d)},
            state_delta={"last_action": f"copied {s.name}", "result": f"copy saved at {d}"}
        )
    except PermissionError:
        return AgentResponse.failure(f"Permission denied")
    except Exception as e:
        return AgentResponse.failure(f"Copy failed: {e}")
