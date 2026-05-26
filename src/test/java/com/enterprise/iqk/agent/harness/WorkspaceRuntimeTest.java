package com.enterprise.iqk.agent.harness;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class WorkspaceRuntimeTest {

    @TempDir
    Path workspace;

    @Test
    void readsSearchesAndWritesInsideWorkspace() throws Exception {
        Files.writeString(workspace.resolve("README.md"), "hello harness\nsecond line", StandardCharsets.UTF_8);
        WorkspaceRuntime runtime = new WorkspaceRuntime(workspace);

        AgentObservation read = runtime.execute(action("workspace_read_file", Map.of("path", "README.md")));
        AgentObservation search = runtime.execute(action("workspace_search_text",
                Map.of("query", "harness", "path", ".")));
        AgentObservation write = runtime.execute(action("workspace_apply_patch",
                Map.of("path", "notes/result.txt", "content", "done")));

        assertThat(read.toMap()).containsEntry("content", "hello harness\nsecond line");
        assertThat((List<?>) search.toMap().get("matches")).hasSize(1);
        assertThat(write.toMap()).containsEntry("status", "written");
        assertThat(Files.readString(workspace.resolve("notes/result.txt"))).isEqualTo("done");
    }

    @Test
    void rejectsPathsOutsideWorkspace() {
        WorkspaceRuntime runtime = new WorkspaceRuntime(workspace);

        AgentObservation observation = runtime.execute(action("workspace_read_file", Map.of("path", "../outside.txt")));

        assertThat(observation.toMap())
                .containsEntry("status", "error")
                .containsEntry("source", "workspace");
        assertThat((String) observation.toMap().get("message")).contains("path escapes workspace root");
    }

    @Test
    void runsOnlyAllowedCommandFamilies() {
        WorkspaceRuntime runtime = new WorkspaceRuntime(workspace);

        AgentObservation denied = runtime.execute(action("workspace_run_shell", Map.of("command", "rm -rf .")));
        AgentObservation deniedGitPush = runtime.execute(action("workspace_run_shell", Map.of("command", "git push")));
        AgentObservation allowed = runtime.execute(action("workspace_run_shell", Map.of("command", "pwd")));

        assertThat(denied.toMap()).containsEntry("status", "error");
        assertThat(deniedGitPush.toMap()).containsEntry("status", "error");
        assertThat(allowed.toMap()).containsEntry("exitCode", 0);
        assertThat((String) allowed.toMap().get("stdout")).contains(workspace.toString());
    }

    @Test
    void proposesAndAppliesUnifiedDiffPatch() throws Exception {
        Files.writeString(workspace.resolve("README.md"), "old line", StandardCharsets.UTF_8);
        WorkspaceRuntime runtime = new WorkspaceRuntime(workspace);

        AgentObservation preview = runtime.execute(action("workspace_propose_patch",
                Map.of("path", "README.md", "content", "new line")));
        String patch = String.valueOf(preview.toMap().get("patch"));
        AgentObservation applied = runtime.execute(action("workspace_apply_patch",
                Map.of("path", "README.md", "patch", patch)));

        assertThat(patch).contains("--- a/README.md", "+++ b/README.md");
        assertThat(applied.toMap()).containsEntry("status", "written");
        assertThat(Files.readString(workspace.resolve("README.md"))).isEqualTo("new line");
    }

    private AgentAction action(String action, Map<String, Object> input) {
        return new AgentAction(action, input, "prompt", "tenant", "chat",
                "balanced", "task-1", "step-1", true);
    }
}
