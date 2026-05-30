import { Injectable } from "@nestjs/common";

import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { PlatformStore, WorkflowTask } from "../platform/platform.store.js";

@Injectable()
export class WorkflowService {
  constructor(private readonly store: PlatformStore) {}

  createTask(tenantId: string | undefined, type: string, userInput: string, modelProfile?: string): WorkflowTask {
    const task: WorkflowTask = {
      taskId: newId("task"),
      tenantId: normalizeTenant(tenantId),
      type,
      status: "DONE",
      userInput,
      finalOutput: `TypeScript ${type} scaffold result for: ${userInput}`,
      modelProfile,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    this.store.workflowTasks.set(task.taskId, task);
    this.store.workflowEvents.set(task.taskId, [
      {
        eventId: newId("evt"),
        taskId: task.taskId,
        eventType: "DONE",
        payload: { status: "DONE" },
        createdAt: nowIso()
      }
    ]);
    return task;
  }

  getTask(taskId: string) {
    return this.store.workflowTasks.get(taskId);
  }

  listTasks(tenantId: string, page: number, pageSize: number) {
    const start = (Math.max(page, 1) - 1) * pageSize;
    return [...this.store.workflowTasks.values()]
      .filter((task) => task.tenantId === normalizeTenant(tenantId))
      .slice(start, start + pageSize);
  }

  getEvents(taskId: string) {
    return this.store.workflowEvents.get(taskId) ?? [];
  }
}
