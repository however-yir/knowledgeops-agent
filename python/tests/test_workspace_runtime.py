from __future__ import annotations

from knowledgeops_py.infrastructure.workspace_runtime import WorkspaceRuntime, apply_unified_diff


def runtime(tmp_path, *, write_enabled: bool = False, shell_enabled: bool = False, max_file_bytes: int = 20_000) -> WorkspaceRuntime:
    return WorkspaceRuntime(
        root=tmp_path,
        write_enabled=write_enabled,
        shell_enabled=shell_enabled,
        max_file_bytes=max_file_bytes,
    )


def test_workspace_runtime_reads_lists_searches_and_rejects_path_escapes(tmp_path) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "policy.txt").write_text("Heat safety requires water and shade.\n", encoding="utf-8")
    workspace = runtime(tmp_path, max_file_bytes=12)

    listed = workspace.execute("workspace_list_files", {"path": "notes", "maxDepth": 2})
    read = workspace.execute("workspace_read_file", {"path": "notes/policy.txt"})
    searched = workspace.execute("workspace_search_text", {"query": "shade", "path": "notes"})
    escaped = workspace.execute("workspace_read_file", {"path": "../secret.txt"})

    assert listed["status"] == "success" and listed["files"][0]["path"] == "notes"
    assert read["content"] == "Heat safety " and read["truncated"] is True
    assert searched["matches"] == [{"path": "notes/policy.txt", "lineNumber": 1, "line": "Heat safety requires water and shade."}]
    assert escaped["status"] == "error" and "path escapes workspace root" in escaped["message"]


def test_workspace_runtime_proposes_and_applies_bounded_patches(tmp_path) -> None:
    target = tmp_path / "note.txt"
    target.write_text("before\n", encoding="utf-8")
    writable = runtime(tmp_path, write_enabled=True)

    proposal = writable.execute(
        "workspace_propose_patch",
        {"path": "note.txt", "content": "after\n", "summary": "replace draft"},
    )
    applied = writable.execute("workspace_apply_patch", {"path": "note.txt", "patch": proposal["patch"]})
    denied = runtime(tmp_path).execute("workspace_apply_patch", {"path": "other.txt", "content": "nope"})

    assert proposal["status"] == "success" and "-before" in proposal["patch"] and "+after" in proposal["patch"]
    assert applied == {"status": "written", "path": "note.txt", "bytes": 5, "source": "workspace", "latencyMs": applied["latencyMs"]}
    assert target.read_text(encoding="utf-8") == "after"
    assert denied["status"] == "error" and denied["message"] == "workspace writes are disabled"


def test_workspace_runtime_enforces_shell_allowlist_and_output_shape(tmp_path) -> None:
    workspace = runtime(tmp_path, shell_enabled=True)

    pwd = workspace.execute("workspace_run_shell", {"command": "pwd"})
    denied = workspace.execute("workspace_run_shell", {"command": "python -V"})
    disabled = runtime(tmp_path).execute("workspace_run_shell", {"command": "pwd"})

    assert pwd["status"] == "success" and pwd["exitCode"] == 0 and pwd["stdout"].strip() == str(tmp_path)
    assert denied["status"] == "error" and denied["message"] == "command is not allowed"
    assert disabled["status"] == "error" and disabled["message"] == "workspace shell is disabled"


def test_apply_unified_diff_rejects_mismatched_context() -> None:
    assert apply_unified_diff("before\n", "@@ -1 +1 @@\n-before\n+after\n") == "after"
    try:
        apply_unified_diff("before\n", "@@ -1 +1 @@\n-other\n+after\n")
    except ValueError as error:
        assert str(error) == "patch removal does not match workspace file"
    else:
        raise AssertionError("expected invalid diff to be rejected")


def test_workspace_shell_ls_and_rg_arguments_must_stay_in_root(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.py").write_text("value = 1\n", encoding="utf-8")
    workspace = runtime(tmp_path, shell_enabled=True)

    inside = workspace.execute("workspace_run_shell", {"command": "rg value src"})
    flags_only = workspace.execute("workspace_run_shell", {"command": "ls -la"})
    listing = workspace.execute("workspace_run_shell", {"command": "ls src"})

    assert inside["status"] == "success" and inside["exitCode"] == 0
    assert flags_only["status"] == "success"
    assert listing["status"] == "success" and "code.py" in listing["stdout"]

    for command in ("rg value /etc/passwd", "rg value ../secret.txt", "ls /etc", "ls ..", "rg -e value /etc/passwd"):
        result = workspace.execute("workspace_run_shell", {"command": command})
        assert result["status"] == "error", command
        assert result["message"] == "command is not allowed", command


def test_workspace_shell_rg_accepts_pattern_and_rooted_paths(tmp_path) -> None:
    (tmp_path / "readme.md").write_text("hello world\n", encoding="utf-8")
    workspace = runtime(tmp_path, shell_enabled=True)

    pattern_only = workspace._allowed_command(["rg", "hello.*world"])
    separator = workspace._allowed_command(["rg", "--", "--pattern-like"])
    rooted = workspace._allowed_command(["rg", "hello", "readme.md"])
    outside = workspace._allowed_command(["rg", "hello", "/etc/passwd"])

    assert pattern_only is True
    assert separator is True
    assert rooted is True
    assert outside is False
