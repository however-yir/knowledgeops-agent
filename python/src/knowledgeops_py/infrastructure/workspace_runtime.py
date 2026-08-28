"""Bounded local workspace runtime used by trusted Harness actions."""

from __future__ import annotations

import difflib

# Shell execution is constrained to a validated argv allowlist below.
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkspaceRuntime:
    root: Path
    write_enabled: bool
    shell_enabled: bool
    command_timeout_seconds: int = 10
    max_command_output_bytes: int = 12_000
    max_file_bytes: int = 20_000
    max_search_files: int = 1_000
    allowed_commands: tuple[str, ...] = ("pwd", "ls", "rg", "git", "mvn")
    allowed_git_subcommands: tuple[str, ...] = ("status", "diff", "show", "log", "rev-parse", "branch")

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def execute(self, action: str, action_input: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        try:
            payload = self._execute(action, action_input)
            status = str(payload.pop("status", "success"))
            result = {"status": status, **payload, "source": "workspace", "latencyMs": elapsed_ms(started)}
            if status == "error":
                result["message"] = str(payload.get("message") or "workspace action failed")
            return result
        except (OSError, ValueError) as exc:
            return {
                "status": "error",
                "source": "workspace",
                "latencyMs": elapsed_ms(started),
                "message": f"workspace action failed: {exc}",
            }

    def _execute(self, action: str, action_input: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace_list_files":
            return self._list_files(action_input)
        if action == "workspace_read_file":
            return self._read_file(action_input)
        if action == "workspace_search_text":
            return self._search_text(action_input)
        if action == "workspace_propose_patch":
            return self._propose_patch(action_input)
        if action == "workspace_apply_patch":
            return self._apply_patch(action_input)
        if action == "workspace_run_shell":
            return self._run_shell(action_input)
        return {"status": "error", "message": f"unsupported action: {action}"}

    def _list_files(self, action_input: dict[str, Any]) -> dict[str, Any]:
        root = self._resolve_path(string_value(action_input, "path", "."))
        max_depth = min(max(integer_value(action_input.get("maxDepth"), 2), 0), 5)
        files = [self._file_summary(root)]
        for candidate in sorted(root.rglob("*")):
            if len(candidate.relative_to(root).parts) > max_depth:
                continue
            files.append(self._file_summary(candidate))
            if len(files) >= 200:
                break
        return {"root": self._relative(root), "files": files}

    def _read_file(self, action_input: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(string_value(action_input, "path", ""))
        if not path.is_file():
            return {"status": "error", "message": f"file not found: {self._relative(path)}"}
        max_bytes = min(max(integer_value(action_input.get("maxBytes"), self.max_file_bytes), 1), self.max_file_bytes)
        content = path.read_bytes()[:max_bytes]
        return {
            "path": self._relative(path),
            "content": content.decode("utf-8", errors="replace"),
            "truncated": path.stat().st_size > len(content),
        }

    def _search_text(self, action_input: dict[str, Any]) -> dict[str, Any]:
        query = string_value(action_input, "query", "")
        root = self._resolve_path(string_value(action_input, "path", "."))
        max_matches = min(max(integer_value(action_input.get("maxMatches"), 50), 1), 100)
        matches: list[dict[str, Any]] = []
        candidates = (candidate for candidate in root.rglob("*") if candidate.is_file())
        for index, path in enumerate(candidates):
            if index >= max(1, self.max_search_files) or len(matches) >= max_matches:
                break
            if path.stat().st_size > 1_000_000:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    matches.append({"path": self._relative(path), "lineNumber": line_number, "line": line})
                    if len(matches) >= max_matches:
                        break
        return {"query": query, "matches": matches}

    def _propose_patch(self, action_input: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(string_value(action_input, "path", ""))
        content = string_value(action_input, "content", "")
        patch = string_value(action_input, "patch", "")
        old_content = path.read_text(encoding="utf-8") if path.is_file() else ""
        rendered_patch = patch or "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=self._relative(path),
                tofile=self._relative(path),
            )
        )
        return {
            "path": self._relative(path),
            "summary": string_value(action_input, "summary", ""),
            "contentBytes": len(content.encode()),
            "patch": rendered_patch,
            "wouldCreate": not path.exists(),
            "applyAction": "workspace_apply_patch",
        }

    def _apply_patch(self, action_input: dict[str, Any]) -> dict[str, Any]:
        if not self.write_enabled:
            return {"status": "error", "message": "workspace writes are disabled"}
        path = self._resolve_path(string_value(action_input, "path", ""))
        content = string_value(action_input, "content", "")
        patch = string_value(action_input, "patch", "")
        old_content = path.read_text(encoding="utf-8") if path.is_file() else ""
        next_content = apply_unified_diff(old_content, patch) if patch else content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(next_content, encoding="utf-8")
        return {"status": "written", "path": self._relative(path), "bytes": len(next_content.encode())}

    def _run_shell(self, action_input: dict[str, Any]) -> dict[str, Any]:
        if not self.shell_enabled:
            return {"status": "error", "message": "workspace shell is disabled"}
        command = string_value(action_input, "command", "").split()
        if not self._allowed_command(command):
            return {"status": "error", "message": "command is not allowed"}
        timeout = min(max(integer_value(action_input.get("timeoutSeconds"), self.command_timeout_seconds), 1), 30)
        try:
            # _allowed_command validates the executable and all privileged subcommands.
            completed = subprocess.run(  # nosec B603
                command,
                cwd=self.root,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "command timed out"}
        stdout, stdout_truncated = truncate_bytes(completed.stdout, self.max_command_output_bytes)
        stderr, stderr_truncated = truncate_bytes(completed.stderr, self.max_command_output_bytes)
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        return {
            "exitCode": completed.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "output": stdout_text + stderr_text,
            "truncated": stdout_truncated or stderr_truncated,
        }

    def _resolve_path(self, raw_path: str) -> Path:
        path = (self.root / (raw_path or ".")).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("path escapes workspace root")
        return path

    def _relative(self, path: Path) -> str:
        return "." if path == self.root else path.relative_to(self.root).as_posix()

    def _file_summary(self, path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"path": self._relative(path), "type": "directory" if path.is_dir() else "file"}
        if path.is_file():
            result["size"] = path.stat().st_size
        return result

    def _allowed_command(self, command: list[str]) -> bool:
        if not command or command[0] not in self.allowed_commands:
            return False
        if command[0] == "pwd":
            return len(command) == 1
        if command[0] in {"ls", "rg"}:
            return self._args_within_workspace(command)
        if command[0] == "git":
            return len(command) >= 2 and command[1] in self.allowed_git_subcommands
        return command[0] == "mvn" and "test" in command and all(
            item in {"mvn", "test", "-q"} or item.startswith("-D") for item in command
        )

    def _args_within_workspace(self, command: list[str]) -> bool:
        """Every path-like argument of ls/rg must stay inside the workspace root.

        Mirrors the Java WorkspaceRuntime.argsWithinWorkspace hardening: both
        commands accept path arguments, so without this check an agent could
        read arbitrary host files (e.g. ``rg pattern /etc/passwd``). For rg the
        first non-flag argument is the search pattern, not a path; anything
        that is not unambiguously a workspace path fails closed.
        """
        pattern_pending = command[0] == "rg"
        seen_separator = False
        for item in command[1:]:
            if not seen_separator and item == "--":
                seen_separator = True
                continue
            if not seen_separator and item.startswith("-"):
                continue
            if pattern_pending:
                pattern_pending = False
                continue
            resolved = (self.root / item).resolve()
            if not resolved.is_relative_to(self.root):
                return False
        return True


def apply_unified_diff(original: str, patch: str) -> str:
    if not patch.strip():
        return original
    original_lines = java_diff_lines(original)
    patch_lines = java_diff_lines(patch)
    result: list[str] = []
    source_index = 0
    line_index = 0
    while line_index < len(patch_lines):
        line = patch_lines[line_index]
        if line.startswith(("---", "+++")):
            line_index += 1
            continue
        if not line.startswith("@@"):
            line_index += 1
            continue
        header = line.split(" ")
        old_range = header[1]
        old_start = int(old_range[1:].split(",")[0]) - 1
        result.extend(original_lines[source_index:old_start])
        source_index = old_start
        line_index += 1
        while line_index < len(patch_lines) and not patch_lines[line_index].startswith("@@"):
            change = patch_lines[line_index]
            marker, content = change[:1], change[1:]
            if marker == " ":
                if source_index >= len(original_lines) or original_lines[source_index] != content:
                    raise ValueError("patch context does not match workspace file")
                result.append(original_lines[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(original_lines) or original_lines[source_index] != content:
                    raise ValueError("patch removal does not match workspace file")
                source_index += 1
            elif marker == "+":
                result.append(content)
            elif marker != "\\":
                raise ValueError("invalid unified diff")
            line_index += 1
    result.extend(original_lines[source_index:])
    return "\n".join(result)


def java_diff_lines(value: str) -> list[str]:
    trimmed = value[:-1] if value.endswith("\n") else value
    return trimmed.split("\n") if trimmed else []


def truncate_bytes(value: bytes, limit: int) -> tuple[bytes, bool]:
    size = max(1, limit)
    return (value[:size], len(value) > size)


def string_value(values: dict[str, Any], key: str, fallback: str) -> str:
    value = values.get(key)
    return str(value).strip() if value is not None and str(value).strip() else fallback


def integer_value(value: Any, fallback: int) -> int:
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))
