<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-block">
        <p class="eyebrow">KnowledgeOps Agent</p>
        <h1>Chat Console</h1>
        <p class="brand-sub">面向知识运营团队的 ReAct 工作台</p>
      </div>

      <button class="new-chat-btn" type="button" @click="createAndSwitchSession">+ 新建会话</button>

      <section class="session-tools">
        <el-input v-model="sessionSearch" size="small" placeholder="搜索会话标题或 ID" clearable />
        <div class="tool-row">
          <el-select v-model="workspaceFilter" size="small" class="tool-select">
            <el-option label="全部工作区" value="all" />
            <el-option
              v-for="workspace in workspaceOptions"
              :key="workspace"
              :label="workspace"
              :value="workspace"
            />
          </el-select>
          <el-switch
            v-model="showArchivedSessions"
            size="small"
            inline-prompt
            active-text="含归档"
            inactive-text="隐藏归档"
          />
        </div>
      </section>

      <section class="session-panel">
        <div class="section-head">
          <p class="section-label">会话</p>
          <span class="section-meta">{{ filteredSessions.length }}/{{ sessionCount }}</span>
        </div>
        <div class="session-list">
          <div
            v-for="session in filteredSessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === activeSessionId }"
            role="button"
            tabindex="0"
            @click="switchSession(session.id)"
            @keydown.enter.prevent="switchSession(session.id)"
          >
            <div class="session-content">
              <div class="session-title-row">
                <p class="session-title">{{ session.title }}</p>
                <el-tag v-if="session.pinned" size="small" type="success" effect="plain">置顶</el-tag>
                <el-tag v-if="session.archived" size="small" type="info" effect="plain">归档</el-tag>
              </div>
              <p class="session-meta-row">{{ session.workspaceId }} · {{ formatTime(session.updatedAt) }} · {{ shortId(session.id) }}</p>
            </div>
            <div class="session-actions">
              <button type="button" @click.stop="toggleSessionPin(session.id)">{{ session.pinned ? '取消置顶' : '置顶' }}</button>
              <button type="button" @click.stop="toggleSessionArchive(session.id)">{{ session.archived ? '取消归档' : '归档' }}</button>
              <button type="button" class="danger" @click.stop="removeSession(session.id)">删除</button>
            </div>
          </div>
          <div v-if="filteredSessions.length === 0" class="session-empty">没有匹配会话</div>
        </div>
      </section>

      <section class="branch-panel">
        <div class="section-head">
          <p class="section-label">分支树</p>
          <div class="branch-head-actions">
            <span class="section-meta">{{ activeSession?.branches.length ?? 0 }} 条</span>
            <button type="button" @click="forkFromCurrent">从当前分叉</button>
          </div>
        </div>
        <div class="branch-list">
          <div
            v-for="node in branchTreeItems"
            :key="node.branch.id"
            class="branch-item"
            :class="{ active: node.branch.id === activeBranch?.id }"
            :style="{ paddingLeft: `${12 + node.depth * 14}px` }"
            role="button"
            tabindex="0"
            @click="switchBranch(node.branch.id)"
            @keydown.enter.prevent="switchBranch(node.branch.id)"
          >
            <span class="branch-line" :style="{ opacity: node.depth > 0 ? 1 : 0 }"></span>
            <div class="branch-content">
              <p>{{ node.branch.title }}</p>
              <small>{{ formatTime(node.branch.updatedAt) }}</small>
            </div>
          </div>
          <div v-if="branchTreeItems.length === 0" class="session-empty">暂无分支</div>
        </div>
      </section>

      <details class="ops-panel" open>
        <summary><span>鉴权与模型</span></summary>
        <div class="ops-body">
          <el-form label-position="top" size="small">
            <el-form-item label="API Key">
              <el-input
                v-model="apiKeyInput"
                placeholder="输入 API Key（生产建议短时使用）"
                show-password
                type="password"
              />
            </el-form-item>
            <el-form-item label="Tenant (可选)">
              <el-input v-model="tenantInput" placeholder="public" />
            </el-form-item>
            <el-form-item label="Model Profile">
              <el-segmented
                v-model="modelProfile"
                :options="['economy', 'balanced', 'quality']"
                class="full-width"
              />
            </el-form-item>
            <el-form-item label="响应模式">
              <el-switch v-model="streaming" inline-prompt active-text="SSE" inactive-text="JSON" />
            </el-form-item>
          </el-form>
          <div class="auth-buttons">
            <el-button type="primary" :loading="authLoading" @click="handleLogin">换取 JWT</el-button>
            <el-button :disabled="!refreshToken" :loading="refreshing" @click="handleRefresh">刷新</el-button>
            <el-button @click="clearAuth">清空</el-button>
          </div>
        </div>
      </details>
    </aside>

    <main class="workspace">
      <header class="workspace-head">
        <div>
          <p class="workspace-kicker">Active Session</p>
          <h2>{{ activeSession?.title || '新会话' }}</h2>
          <p class="workspace-sub">{{ modelProfile }} · {{ streaming ? 'SSE 流式' : 'JSON 单次' }}</p>
        </div>
        <div class="head-actions">
          <el-select v-model="activeWorkspaceId" size="small" class="workspace-select">
            <el-option
              v-for="workspace in workspaceOptions"
              :key="workspace"
              :label="workspace"
              :value="workspace"
            />
          </el-select>
          <el-input
            v-model="workspaceDraft"
            size="small"
            class="workspace-input"
            placeholder="新工作区"
            @keydown.enter.prevent="createWorkspace"
          />
          <el-button size="small" @click="createWorkspace">创建并切换</el-button>
          <el-switch
            v-model="darkMode"
            inline-prompt
            active-text="Dark"
            inactive-text="Light"
          />
          <el-tag :type="streamStatusTagType" effect="plain">{{ streamStatusLabel }}</el-tag>
          <span class="stream-detail">{{ streamStatusDetail }}</span>
          <el-button size="small" @click="clearConversation">清空会话</el-button>
        </div>
      </header>

      <section
        ref="messageContainer"
        class="messages"
        @scroll="onMessageScroll"
        @click="handleMarkdownClick"
      >
        <div v-if="hydrating" class="hydration-skeleton">
          <div class="skeleton-line lg"></div>
          <div class="skeleton-line"></div>
          <div class="skeleton-line short"></div>
          <div class="skeleton-bubble"></div>
          <div class="skeleton-bubble alt"></div>
        </div>

        <template v-else>
          <div v-if="isEmptyConversation" class="welcome-block">
            <h3>开始一个新问题</h3>
            <p>支持消息编辑后重发分支、流式轨迹、长会话虚拟渲染。</p>
            <div class="welcome-prompts">
              <button v-for="sample in quickPrompts" :key="sample" type="button" @click="prompt = sample">
                {{ sample }}
              </button>
            </div>
          </div>

          <div class="virtual-spacer" :style="{ height: `${virtualTopSpacer}px` }"></div>

          <article
            v-for="entry in virtualMessages"
            :key="entry.item.id"
            :data-msg-id="entry.item.id"
            class="message-row"
            :class="[entry.item.role, entry.item.state || 'done']"
            :ref="(el) => setMessageRowRef(entry.item.id, el as HTMLElement | null)"
          >
            <div class="avatar">{{ entry.item.role === 'user' ? 'U' : 'AI' }}</div>
            <div class="bubble-wrap">
              <div class="bubble-meta">
                <span>{{ entry.item.role === 'user' ? 'You' : 'Assistant' }}</span>
                <span>{{ formatTime(entry.item.createdAt) }}</span>
                <span v-if="entry.item.state === 'streaming'" class="status-dot">生成中</span>
                <span v-if="entry.item.state === 'pending'" class="status-dot">思考中</span>
              </div>

              <div class="bubble">
                <template v-if="entry.item.role === 'assistant'">
                  <div v-if="entry.item.state === 'pending' && !entry.item.content" class="assistant-skeleton">
                    <div></div>
                    <div></div>
                    <div></div>
                  </div>
                  <div v-else class="markdown" v-html="renderMarkdown(entry.item.content)"></div>
                </template>

                <template v-else>
                  <div v-if="editingMessageId === entry.item.id" class="edit-box">
                    <el-input
                      v-model="editingMessageDraft"
                      type="textarea"
                      :rows="3"
                      resize="none"
                    />
                    <div class="edit-actions">
                      <el-button size="small" @click="cancelEditMessage">取消</el-button>
                      <el-button
                        size="small"
                        type="primary"
                        :disabled="!editingMessageDraft.trim() || sending"
                        @click="submitEditAndResend(entry.index, entry.item.id)"
                      >
                        编辑后重发分支
                      </el-button>
                    </div>
                  </div>
                  <p v-else class="plain">{{ entry.item.content }}</p>
                </template>
              </div>

              <div class="message-actions">
                <button type="button" @click="copyMessage(entry.item.content)">复制</button>
                <button
                  v-if="entry.item.role === 'assistant'"
                  type="button"
                  @click="regenerateFrom(entry.index)"
                >
                  重试分支
                </button>
                <button
                  v-if="entry.item.role === 'user'"
                  type="button"
                  @click="startEditMessage(entry.item)"
                >
                  编辑后重发
                </button>
              </div>
            </div>
          </article>

          <div class="virtual-spacer" :style="{ height: `${virtualBottomSpacer}px` }"></div>

          <div v-if="sending && isStreamingResponse" class="thinking">
            {{ streamStatusLabel }} · {{ streamStatusDetail || '处理中...' }}
          </div>
        </template>
      </section>

      <footer class="composer-shell">
        <div class="composer">
          <el-input
            v-model="prompt"
            class="composer-input"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
            @keydown.enter.exact.prevent="send"
          />
          <div class="composer-footer">
            <div class="quick-prompts">
              <button
                v-for="sample in quickPrompts"
                :key="sample"
                type="button"
                @click="prompt = sample"
              >
                {{ sample }}
              </button>
            </div>
            <div class="composer-actions">
              <el-button :disabled="!sending" @click="stopGenerating">停止</el-button>
              <el-button type="primary" :loading="sending" :disabled="!prompt.trim() || sending" @click="send">发送</el-button>
            </div>
          </div>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/core";
import bashLang from "highlight.js/lib/languages/bash";
import javaLang from "highlight.js/lib/languages/java";
import javascriptLang from "highlight.js/lib/languages/javascript";
import jsonLang from "highlight.js/lib/languages/json";
import markdownLang from "highlight.js/lib/languages/markdown";
import pythonLang from "highlight.js/lib/languages/python";
import sqlLang from "highlight.js/lib/languages/sql";
import typescriptLang from "highlight.js/lib/languages/typescript";
import xmlLang from "highlight.js/lib/languages/xml";
import yamlLang from "highlight.js/lib/languages/yaml";
import { ElMessage } from "element-plus";
import { marked } from "marked";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { exchangeApiKey, reactChat, refreshJwt, streamReactChat } from "./api/client";
import type {
  ReactChatResponse,
  ReactErrorEvent,
  ReactTokenEvent,
  ReactTraceStep
} from "./types/react";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  state?: "pending" | "streaming" | "done" | "error" | "stopped";
}

interface SessionBranch {
  id: string;
  title: string;
  parentBranchId: string | null;
  parentMessageId: string | null;
  updatedAt: number;
  messages: ChatMessage[];
  traceSteps: ReactTraceStep[];
}

interface SessionRecord {
  id: string;
  title: string;
  updatedAt: number;
  modelProfile: string;
  streaming: boolean;
  pinned: boolean;
  archived: boolean;
  workspaceId: string;
  activeBranchId: string;
  branches: SessionBranch[];
}

interface BranchTreeItem {
  branch: SessionBranch;
  depth: number;
}

interface MessageMetric {
  item: ChatMessage;
  index: number;
  offset: number;
  height: number;
}

type StreamPhase = "idle" | "thinking" | "tool" | "streaming" | "done" | "error" | "stopped";

const STORAGE_KEY = "knowledgeops-agent-react-console-v2";
const LEGACY_STORAGE_KEY = "knowledgeops-agent-react-console";
const DEFAULT_SYSTEM_MESSAGE = "欢迎使用 ReAct 控制台。你可以先输入 API Key 获取 JWT，然后发起带轨迹的问答。";
const DEFAULT_WORKSPACE = "default";
const ESTIMATED_ROW_HEIGHT = 156;
const OVERSCAN_COUNT = 8;

hljs.registerLanguage("bash", bashLang);
hljs.registerLanguage("java", javaLang);
hljs.registerLanguage("javascript", javascriptLang);
hljs.registerLanguage("json", jsonLang);
hljs.registerLanguage("markdown", markdownLang);
hljs.registerLanguage("python", pythonLang);
hljs.registerLanguage("sql", sqlLang);
hljs.registerLanguage("typescript", typescriptLang);
hljs.registerLanguage("xml", xmlLang);
hljs.registerLanguage("yaml", yamlLang);

function safeParse(raw: string | null): Record<string, unknown> {
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toBase64(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function fromBase64(value: string): string {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

const renderer = new marked.Renderer();
renderer.code = ((token: { text: string; lang?: string }) => {
  const rawCode = token.text ?? "";
  const lang = token.lang?.trim().toLowerCase().split(/\s+/)[0] ?? "plaintext";
  const language = hljs.getLanguage(lang) ? lang : "plaintext";
  const highlighted = language === "plaintext"
    ? escapeHtml(rawCode)
    : hljs.highlight(rawCode, { language, ignoreIllegals: true }).value;

  const lines = highlighted.split("\n");
  const numbered = lines
    .map((line, index) => {
      const content = line || "&nbsp;";
      return `<span class=\"code-line\"><span class=\"line-no\">${index + 1}</span><span class=\"line-content\">${content}</span></span>`;
    })
    .join("");

  const payload = escapeHtml(toBase64(rawCode));

  return `<div class=\"code-block\"><div class=\"code-toolbar\"><span class=\"code-lang\">${language}</span><button class=\"copy-code-btn\" type=\"button\" data-code=\"${payload}\">复制代码</button></div><pre><code class=\"hljs language-${language}\">${numbered}</code></pre></div>`;
}) as typeof renderer.code;

marked.use({
  gfm: true,
  breaks: true,
  renderer
});

function createChatId(): string {
  const suffix = Math.random().toString(36).slice(2, 8);
  return `react-${Date.now()}-${suffix}`;
}

function createBranchId(): string {
  const suffix = Math.random().toString(36).slice(2, 8);
  return `branch-${Date.now()}-${suffix}`;
}

function createMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    createdAt: Date.now(),
    state: "done"
  };
}

function normalizeMessage(raw: unknown): ChatMessage {
  const candidate = (raw ?? {}) as Partial<ChatMessage>;
  const role = candidate.role === "assistant" ? "assistant" : "user";
  return {
    id: candidate.id || `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content: typeof candidate.content === "string" ? candidate.content : "",
    createdAt: typeof candidate.createdAt === "number" ? candidate.createdAt : Date.now(),
    state: candidate.state || "done"
  };
}

function deriveTitle(text: string): string {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) {
    return "新会话";
  }
  return clean.length > 28 ? `${clean.slice(0, 28)}...` : clean;
}

function createRootBranch(): SessionBranch {
  return {
    id: createBranchId(),
    title: "主分支",
    parentBranchId: null,
    parentMessageId: null,
    updatedAt: Date.now(),
    messages: [createMessage("assistant", DEFAULT_SYSTEM_MESSAGE)],
    traceSteps: []
  };
}

function normalizeBranch(raw: unknown): SessionBranch {
  const candidate = (raw ?? {}) as Partial<SessionBranch>;
  const messages = Array.isArray(candidate.messages)
    ? candidate.messages.map(normalizeMessage)
    : [createMessage("assistant", DEFAULT_SYSTEM_MESSAGE)];

  return {
    id: candidate.id || createBranchId(),
    title: candidate.title || "分支",
    parentBranchId: candidate.parentBranchId ?? null,
    parentMessageId: candidate.parentMessageId ?? null,
    updatedAt: typeof candidate.updatedAt === "number" ? candidate.updatedAt : Date.now(),
    messages,
    traceSteps: Array.isArray(candidate.traceSteps) ? candidate.traceSteps : []
  };
}

function normalizeSession(raw: unknown): SessionRecord {
  const candidate = (raw ?? {}) as Record<string, unknown>;
  let branches: SessionBranch[] = [];

  if (Array.isArray(candidate.branches) && candidate.branches.length > 0) {
    branches = candidate.branches.map((item) => normalizeBranch(item));
  } else {
    const fallbackMessages = Array.isArray(candidate.messages)
      ? candidate.messages.map(normalizeMessage)
      : [createMessage("assistant", DEFAULT_SYSTEM_MESSAGE)];

    branches = [
      {
        id: createBranchId(),
        title: "主分支",
        parentBranchId: null,
        parentMessageId: null,
        updatedAt: typeof candidate.updatedAt === "number" ? candidate.updatedAt : Date.now(),
        messages: fallbackMessages,
        traceSteps: Array.isArray(candidate.traceSteps)
          ? (candidate.traceSteps as ReactTraceStep[])
          : []
      }
    ];
  }

  const activeBranchId = typeof candidate.activeBranchId === "string"
    ? candidate.activeBranchId
    : branches[0].id;

  return {
    id: typeof candidate.id === "string" ? candidate.id : createChatId(),
    title: typeof candidate.title === "string" ? candidate.title : "新会话",
    updatedAt: typeof candidate.updatedAt === "number" ? candidate.updatedAt : Date.now(),
    modelProfile: typeof candidate.modelProfile === "string" ? candidate.modelProfile : "balanced",
    streaming: Boolean(candidate.streaming ?? true),
    pinned: Boolean(candidate.pinned),
    archived: Boolean(candidate.archived),
    workspaceId: typeof candidate.workspaceId === "string" ? candidate.workspaceId : DEFAULT_WORKSPACE,
    activeBranchId,
    branches
  };
}

function createSession(): SessionRecord {
  const id = createChatId();
  const rootBranch = createRootBranch();

  return {
    id,
    title: "新会话",
    updatedAt: Date.now(),
    modelProfile: "balanced",
    streaming: true,
    pinned: false,
    archived: false,
    workspaceId: DEFAULT_WORKSPACE,
    activeBranchId: rootBranch.id,
    branches: [rootBranch]
  };
}

function formatTime(value: number): string {
  return new Date(value).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit"
  });
}

function shortId(id: string): string {
  return id.slice(0, 10);
}

function stringify(data: unknown): string {
  if (data === undefined || data === null) {
    return "{}";
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function renderMarkdown(content: string): string {
  if (!content?.trim()) {
    return "<p>等待模型输出...</p>";
  }
  const html = marked.parse(content) as string;
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["data-code"]
  });
}

const cached = safeParse(localStorage.getItem(STORAGE_KEY));
const legacy = safeParse(localStorage.getItem(LEGACY_STORAGE_KEY));
const bootstrap = Object.keys(cached).length > 0 ? cached : legacy;

const darkMode = ref(Boolean(bootstrap.darkMode));
const apiKeyInput = ref((bootstrap.apiKey as string | undefined) ?? "");
const tenantInput = ref((bootstrap.tenantId as string | undefined) ?? "");
const token = ref((bootstrap.token as string | undefined) ?? "");
const refreshToken = ref((bootstrap.refreshToken as string | undefined) ?? "");
const sessionSearch = ref((bootstrap.sessionSearch as string | undefined) ?? "");
const workspaceFilter = ref((bootstrap.workspaceFilter as string | undefined) ?? "all");
const showArchivedSessions = ref(Boolean(bootstrap.showArchivedSessions));

const sessions = ref<SessionRecord[]>(
  Array.isArray(bootstrap.sessions) && bootstrap.sessions.length > 0
    ? (bootstrap.sessions as unknown[]).map((item) => normalizeSession(item))
    : [createSession()]
);

const activeSessionId = ref((bootstrap.activeSessionId as string | undefined) ?? sessions.value[0].id);

const activeSession = computed(() => {
  const found = sessions.value.find((item) => item.id === activeSessionId.value);
  return found ?? sessions.value[0];
});

const activeBranch = computed(() => {
  const session = activeSession.value;
  return session.branches.find((branch) => branch.id === session.activeBranchId) ?? session.branches[0];
});

const chatId = ref(activeSession.value.id);
const modelProfile = ref(activeSession.value.modelProfile);
const streaming = ref(activeSession.value.streaming);
const messages = ref<ChatMessage[]>([...activeBranch.value.messages]);
const traceSteps = ref<ReactTraceStep[]>([...activeBranch.value.traceSteps]);

const authLoading = ref(false);
const refreshing = ref(false);
const sending = ref(false);
const isStreamingResponse = ref(false);
const hydrating = ref(true);
const prompt = ref("");
const messageContainer = ref<HTMLElement | null>(null);
const currentAbortController = ref<AbortController | null>(null);
const workspaceDraft = ref("");
const editingMessageId = ref<string | null>(null);
const editingMessageDraft = ref("");
const streamPhase = ref<StreamPhase>("idle");
const streamStatusDetail = ref("");

const messageHeights = ref<Record<string, number>>({});
const viewportHeight = ref(0);
const scrollTop = ref(0);
const messageRowElements = new Map<string, HTMLElement>();
let resizeObserver: ResizeObserver | null = null;
let streamResetTimer: number | null = null;

const quickPrompts = [
  "先总结这个会话的关键结论，再列出 3 条行动项",
  "帮我按课程类型推荐三门就业导向课程",
  "先检索知识库，再给出本周学习计划"
];

const sessionCount = computed(() => sessions.value.length);

const workspaceOptions = computed(() => {
  const options = new Set<string>([DEFAULT_WORKSPACE]);
  sessions.value.forEach((session) => {
    options.add(session.workspaceId || DEFAULT_WORKSPACE);
  });
  return [...options].sort((a, b) => a.localeCompare(b, "zh-CN"));
});

const activeWorkspaceId = computed({
  get: () => activeSession.value.workspaceId,
  set: (value: string) => {
    activeSession.value.workspaceId = value || DEFAULT_WORKSPACE;
    persistState();
  }
});

const orderedSessions = computed(() =>
  [...sessions.value].sort((a, b) => {
    if (a.pinned !== b.pinned) {
      return Number(b.pinned) - Number(a.pinned);
    }
    return b.updatedAt - a.updatedAt;
  })
);

const filteredSessions = computed(() => {
  const keyword = sessionSearch.value.trim().toLowerCase();
  return orderedSessions.value.filter((session) => {
    if (!showArchivedSessions.value && session.archived) {
      return false;
    }

    if (workspaceFilter.value !== "all" && session.workspaceId !== workspaceFilter.value) {
      return false;
    }

    if (!keyword) {
      return true;
    }

    return session.title.toLowerCase().includes(keyword) || session.id.toLowerCase().includes(keyword);
  });
});

const branchTreeItems = computed<BranchTreeItem[]>(() => {
  const session = activeSession.value;
  const children = new Map<string | null, SessionBranch[]>();

  session.branches.forEach((branch) => {
    const key = branch.parentBranchId ?? null;
    if (!children.has(key)) {
      children.set(key, []);
    }
    children.get(key)?.push(branch);
  });

  children.forEach((list) => {
    list.sort((a, b) => b.updatedAt - a.updatedAt);
  });

  const result: BranchTreeItem[] = [];

  function dfs(parentId: string | null, depth: number): void {
    const list = children.get(parentId) ?? [];
    list.forEach((branch) => {
      result.push({ branch, depth });
      dfs(branch.id, depth + 1);
    });
  }

  dfs(null, 0);
  return result;
});

const isEmptyConversation = computed(() => {
  const nonSystem = messages.value.filter((item) => item.role === "user");
  return nonSystem.length === 0;
});

const messageMetrics = computed<MessageMetric[]>(() => {
  let offset = 0;
  return messages.value.map((item, index) => {
    const height = messageHeights.value[item.id] ?? ESTIMATED_ROW_HEIGHT;
    const metric = {
      item,
      index,
      offset,
      height
    };
    offset += height;
    return metric;
  });
});

const totalVirtualHeight = computed(() => {
  const metrics = messageMetrics.value;
  if (metrics.length === 0) {
    return 0;
  }
  const last = metrics[metrics.length - 1];
  return last.offset + last.height;
});

function findMetricIndexByOffset(targetOffset: number): number {
  const metrics = messageMetrics.value;
  if (metrics.length === 0) {
    return 0;
  }

  let left = 0;
  let right = metrics.length - 1;
  let answer = metrics.length - 1;

  while (left <= right) {
    const mid = (left + right) >> 1;
    const metric = metrics[mid];
    if (metric.offset + metric.height >= targetOffset) {
      answer = mid;
      right = mid - 1;
    } else {
      left = mid + 1;
    }
  }

  return answer;
}

const virtualRange = computed(() => {
  const total = messages.value.length;
  if (total === 0) {
    return { start: 0, end: -1 };
  }

  const startAnchor = Math.max(0, scrollTop.value - viewportHeight.value * 0.8);
  const endAnchor = scrollTop.value + viewportHeight.value * 1.8;

  const start = Math.max(0, findMetricIndexByOffset(startAnchor) - OVERSCAN_COUNT);
  const end = Math.min(total - 1, findMetricIndexByOffset(endAnchor) + OVERSCAN_COUNT);

  return { start, end };
});

const virtualMessages = computed(() => {
  const metrics = messageMetrics.value;
  const { start, end } = virtualRange.value;
  if (end < start) {
    return [];
  }
  return metrics.slice(start, end + 1);
});

const virtualTopSpacer = computed(() => virtualMessages.value[0]?.offset ?? 0);

const virtualBottomSpacer = computed(() => {
  if (virtualMessages.value.length === 0) {
    return 0;
  }

  const last = virtualMessages.value[virtualMessages.value.length - 1];
  return Math.max(0, totalVirtualHeight.value - (last.offset + last.height));
});

const streamStatusLabel = computed(() => {
  switch (streamPhase.value) {
    case "thinking":
      return "思考中";
    case "tool":
      return "工具调用中";
    case "streaming":
      return "输出中";
    case "done":
      return "已完成";
    case "error":
      return "失败";
    case "stopped":
      return "已停止";
    default:
      return "空闲";
  }
});

const streamStatusTagType = computed(() => {
  switch (streamPhase.value) {
    case "thinking":
      return "warning";
    case "tool":
      return "success";
    case "streaming":
      return "primary";
    case "done":
      return "success";
    case "error":
      return "danger";
    case "stopped":
      return "info";
    default:
      return "info";
  }
});

function scheduleStreamReset(): void {
  if (streamResetTimer) {
    window.clearTimeout(streamResetTimer);
  }
  streamResetTimer = window.setTimeout(() => {
    streamPhase.value = "idle";
    streamStatusDetail.value = "";
    streamResetTimer = null;
  }, 1800);
}

function persistState(): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      darkMode: darkMode.value,
      apiKey: apiKeyInput.value,
      tenantId: tenantInput.value,
      token: token.value,
      refreshToken: refreshToken.value,
      activeSessionId: activeSessionId.value,
      sessionSearch: sessionSearch.value,
      workspaceFilter: workspaceFilter.value,
      showArchivedSessions: showArchivedSessions.value,
      sessions: sessions.value
    })
  );
}

function authContext() {
  return {
    token: token.value || undefined,
    apiKey: apiKeyInput.value || undefined,
    tenantId: tenantInput.value || undefined
  };
}

function getSession(sessionId: string): SessionRecord | undefined {
  return sessions.value.find((item) => item.id === sessionId);
}

function getBranch(session: SessionRecord, branchId: string): SessionBranch | undefined {
  return session.branches.find((branch) => branch.id === branchId);
}

function syncCurrentSessionBranch(): void {
  const session = getSession(activeSessionId.value);
  if (!session) {
    return;
  }

  const branch = getBranch(session, session.activeBranchId);
  if (!branch) {
    return;
  }

  session.modelProfile = modelProfile.value;
  session.streaming = streaming.value;

  branch.messages = [...messages.value];
  branch.traceSteps = [...traceSteps.value];
  branch.updatedAt = Date.now();

  const firstUser = branch.messages.find((item) => item.role === "user");
  if (firstUser?.content?.trim()) {
    branch.title = deriveTitle(firstUser.content);
    session.title = deriveTitle(firstUser.content);
  }

  session.updatedAt = Date.now();
}

function loadSession(sessionId: string): void {
  const session = getSession(sessionId);
  if (!session) {
    return;
  }

  activeSessionId.value = session.id;
  chatId.value = session.id;
  modelProfile.value = session.modelProfile;
  streaming.value = session.streaming;

  const branch = getBranch(session, session.activeBranchId) ?? session.branches[0];
  if (!branch) {
    const rootBranch = createRootBranch();
    session.branches = [rootBranch];
    session.activeBranchId = rootBranch.id;
    messages.value = [...rootBranch.messages];
    traceSteps.value = [...rootBranch.traceSteps];
  } else {
    messages.value = [...branch.messages];
    traceSteps.value = [...branch.traceSteps];
  }

  messageHeights.value = {};
  prompt.value = "";
  editingMessageId.value = null;
  editingMessageDraft.value = "";
  void scrollToBottom(true);
}

function switchSession(sessionId: string): void {
  if (sessionId === activeSessionId.value) {
    return;
  }

  syncCurrentSessionBranch();
  loadSession(sessionId);
  persistState();
}

function createAndSwitchSession(): void {
  syncCurrentSessionBranch();
  const session = createSession();
  sessions.value.unshift(session);
  loadSession(session.id);
  persistState();
}

function removeSession(sessionId: string): void {
  if (sessions.value.length <= 1) {
    ElMessage.warning("至少保留一个会话");
    return;
  }

  syncCurrentSessionBranch();
  const filtered = sessions.value.filter((item) => item.id !== sessionId);
  sessions.value = filtered;

  if (activeSessionId.value === sessionId) {
    const next = filtered.find((item) => !item.archived) ?? filtered[0];
    loadSession(next.id);
  }

  persistState();
}

function toggleSessionPin(sessionId: string): void {
  const session = getSession(sessionId);
  if (!session) {
    return;
  }
  session.pinned = !session.pinned;
  session.updatedAt = Date.now();
  persistState();
}

function toggleSessionArchive(sessionId: string): void {
  const session = getSession(sessionId);
  if (!session) {
    return;
  }

  session.archived = !session.archived;
  session.updatedAt = Date.now();

  if (session.archived && !showArchivedSessions.value && activeSessionId.value === sessionId) {
    const next = sessions.value.find((item) => item.id !== sessionId && !item.archived)
      ?? sessions.value.find((item) => item.id !== sessionId)
      ?? createSession();

    if (!sessions.value.find((item) => item.id === next.id)) {
      sessions.value.unshift(next);
    }

    loadSession(next.id);
  }

  persistState();
}

function createWorkspace(): void {
  const value = workspaceDraft.value.trim().toLowerCase();
  if (!value) {
    return;
  }

  activeWorkspaceId.value = value;
  workspaceFilter.value = value;
  workspaceDraft.value = "";
  persistState();
}

function switchBranch(branchId: string): void {
  const session = activeSession.value;
  if (session.activeBranchId === branchId) {
    return;
  }

  syncCurrentSessionBranch();
  session.activeBranchId = branchId;
  loadSession(session.id);
  persistState();
}

function forkBranch(
  title: string,
  baseMessages: ChatMessage[],
  parentBranchId: string | null,
  parentMessageId: string | null
): SessionBranch {
  return {
    id: createBranchId(),
    title,
    parentBranchId,
    parentMessageId,
    updatedAt: Date.now(),
    messages: [...baseMessages],
    traceSteps: []
  };
}

function forkFromCurrent(): void {
  const session = activeSession.value;
  const current = activeBranch.value;

  const branch = forkBranch(
    `${current.title} · fork`,
    [...messages.value],
    current.id,
    null
  );

  session.branches.unshift(branch);
  session.activeBranchId = branch.id;
  loadSession(session.id);
  persistState();
  ElMessage.success("已创建分支");
}

function startEditMessage(message: ChatMessage): void {
  if (message.role !== "user") {
    return;
  }

  editingMessageId.value = message.id;
  editingMessageDraft.value = message.content;
}

function cancelEditMessage(): void {
  editingMessageId.value = null;
  editingMessageDraft.value = "";
}

async function submitEditAndResend(messageIndex: number, messageId: string): Promise<void> {
  const question = editingMessageDraft.value.trim();
  if (!question) {
    return;
  }

  if (sending.value) {
    ElMessage.warning("请等待当前请求完成");
    return;
  }

  syncCurrentSessionBranch();

  const session = activeSession.value;
  const current = activeBranch.value;
  const baseMessages = messages.value.slice(0, Math.max(0, messageIndex));
  const branch = forkBranch(`${deriveTitle(question)} · edit`, baseMessages, current.id, messageId);

  session.branches.unshift(branch);
  session.activeBranchId = branch.id;
  loadSession(session.id);

  cancelEditMessage();
  persistState();

  await ask(question, true);
}

function upsertTrace(step: ReactTraceStep): void {
  const index = traceSteps.value.findIndex((item) => item.step === step.step);
  if (index >= 0) {
    traceSteps.value[index] = step;
  } else {
    traceSteps.value.push(step);
    traceSteps.value.sort((a, b) => a.step - b.step);
  }
}

function updateViewport(): void {
  viewportHeight.value = messageContainer.value?.clientHeight ?? 0;
}

function onMessageScroll(): void {
  const element = messageContainer.value;
  if (!element) {
    return;
  }
  scrollTop.value = element.scrollTop;
}

function syncMessageHeight(messageId: string, height: number): void {
  if (height <= 0) {
    return;
  }

  const current = messageHeights.value[messageId] ?? 0;
  if (Math.abs(current - height) <= 1) {
    return;
  }

  messageHeights.value = {
    ...messageHeights.value,
    [messageId]: height
  };
}

function setMessageRowRef(messageId: string, element: HTMLElement | null): void {
  const previous = messageRowElements.get(messageId);
  if (previous && previous !== element && resizeObserver) {
    resizeObserver.unobserve(previous);
    messageRowElements.delete(messageId);
  }

  if (!element) {
    return;
  }

  messageRowElements.set(messageId, element);
  syncMessageHeight(messageId, Math.ceil(element.getBoundingClientRect().height));
  if (resizeObserver) {
    resizeObserver.observe(element);
  }
}

async function scrollToBottom(force = false): Promise<void> {
  await nextTick();
  const element = messageContainer.value;
  if (!element) {
    return;
  }

  const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
  if (force || remaining < 180 || sending.value) {
    element.scrollTop = element.scrollHeight;
    scrollTop.value = element.scrollTop;
  }
}

async function handleMarkdownClick(event: MouseEvent): Promise<void> {
  const target = event.target as HTMLElement | null;
  const button = target?.closest(".copy-code-btn") as HTMLElement | null;
  if (!button) {
    return;
  }

  const payload = button.getAttribute("data-code");
  if (!payload) {
    return;
  }

  try {
    const raw = fromBase64(payload);
    await navigator.clipboard.writeText(raw);
    ElMessage.success("代码已复制");
  } catch {
    ElMessage.error("代码复制失败");
  }
}

async function copyMessage(content: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败");
  }
}

function stopGenerating(): void {
  currentAbortController.value?.abort();
}

function clearConversation(): void {
  messages.value = [createMessage("assistant", "会话已重置。你可以继续发问。")];
  traceSteps.value = [];
  prompt.value = "";
  streamPhase.value = "idle";
  streamStatusDetail.value = "";
  syncCurrentSessionBranch();
  persistState();
}

async function handleLogin(): Promise<void> {
  if (!apiKeyInput.value.trim()) {
    ElMessage.warning("请先输入 API Key");
    return;
  }

  authLoading.value = true;
  try {
    const auth = await exchangeApiKey(apiKeyInput.value.trim(), tenantInput.value.trim() || undefined);
    token.value = auth.token ?? "";
    refreshToken.value = auth.refreshToken ?? "";
    if (auth.tenantId) {
      tenantInput.value = auth.tenantId;
    }
    ElMessage.success("JWT 获取成功");
    persistState();
  } catch (error) {
    const message = error instanceof Error ? error.message : "token exchange failed";
    ElMessage.error(message);
  } finally {
    authLoading.value = false;
  }
}

async function handleRefresh(): Promise<void> {
  if (!refreshToken.value) {
    ElMessage.warning("当前没有 refresh token");
    return;
  }

  refreshing.value = true;
  try {
    const auth = await refreshJwt(refreshToken.value);
    token.value = auth.token ?? token.value;
    refreshToken.value = auth.refreshToken ?? refreshToken.value;
    if (auth.tenantId) {
      tenantInput.value = auth.tenantId;
    }
    ElMessage.success("令牌已刷新");
    persistState();
  } catch (error) {
    const message = error instanceof Error ? error.message : "refresh failed";
    ElMessage.error(message);
  } finally {
    refreshing.value = false;
  }
}

function clearAuth(): void {
  token.value = "";
  refreshToken.value = "";
  ElMessage.success("鉴权状态已清空");
  persistState();
}

function sanitizeMessageStates(): void {
  messages.value = messages.value.map((message) => ({
    ...message,
    state: message.state === "pending" || message.state === "streaming" ? "done" : (message.state || "done")
  }));
}

async function ask(question: string, appendUser: boolean): Promise<void> {
  if (!question.trim() || sending.value) {
    return;
  }

  sanitizeMessageStates();

  const assistantMsg: ChatMessage = {
    ...createMessage("assistant", ""),
    state: "pending"
  };

  if (appendUser) {
    messages.value.push(createMessage("user", question));
  }
  messages.value.push(assistantMsg);
  const assistantIndex = messages.value.length - 1;

  traceSteps.value = [];
  sending.value = true;
  isStreamingResponse.value = streaming.value;
  prompt.value = "";
  streamPhase.value = "thinking";
  streamStatusDetail.value = "模型正在准备响应";

  syncCurrentSessionBranch();
  persistState();
  await scrollToBottom(true);

  const controller = new AbortController();
  currentAbortController.value = controller;

  try {
    if (streaming.value) {
      let streamError = "";
      await streamReactChat(
        {
          prompt: question,
          chatId: chatId.value,
          modelProfile: modelProfile.value
        },
        authContext(),
        (event, payload) => {
          if (event === "trace") {
            const step = payload as ReactTraceStep;
            upsertTrace(step);
            streamPhase.value = "tool";
            streamStatusDetail.value = `调用工具: ${step.action}`;
            return;
          }

          if (event === "token") {
            const tokenEvent = payload as ReactTokenEvent;
            messages.value[assistantIndex].state = "streaming";
            messages.value[assistantIndex].content += tokenEvent.token ?? "";
            streamPhase.value = "streaming";
            streamStatusDetail.value = "正在生成文本";
            void scrollToBottom();
            return;
          }

          if (event === "done") {
            const done = payload as ReactChatResponse;
            if (done.trace?.length) {
              traceSteps.value = done.trace;
            }
            if (done.answer?.trim()) {
              messages.value[assistantIndex].content = done.answer;
            }
            messages.value[assistantIndex].state = "done";
            streamPhase.value = "done";
            streamStatusDetail.value = "响应已完成";
            return;
          }

          if (event === "error") {
            const err = payload as ReactErrorEvent;
            streamError = err.message || "stream error";
          }
        },
        controller.signal
      );

      if (streamError) {
        throw new Error(streamError);
      }
    } else {
      const result = await reactChat(
        {
          prompt: question,
          chatId: chatId.value,
          modelProfile: modelProfile.value
        },
        authContext(),
        controller.signal
      );
      traceSteps.value = result.trace ?? [];
      messages.value[assistantIndex].content = result.answer || "模型没有返回内容";
      messages.value[assistantIndex].state = "done";
      streamPhase.value = "done";
      streamStatusDetail.value = "响应已完成";
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      ElMessage.info("已停止输出");
      if (!messages.value[assistantIndex].content.trim()) {
        messages.value[assistantIndex].content = "输出已手动停止。";
      }
      messages.value[assistantIndex].state = "stopped";
      streamPhase.value = "stopped";
      streamStatusDetail.value = "你手动停止了本次输出";
    } else {
      const message = error instanceof Error ? error.message : "request failed";
      messages.value[assistantIndex].content = `请求失败：${message}`;
      messages.value[assistantIndex].state = "error";
      streamPhase.value = "error";
      streamStatusDetail.value = message;
      ElMessage.error(message);
    }
  } finally {
    sending.value = false;
    isStreamingResponse.value = false;
    currentAbortController.value = null;

    syncCurrentSessionBranch();
    persistState();
    await scrollToBottom(true);

    if (streamPhase.value === "done" || streamPhase.value === "error" || streamPhase.value === "stopped") {
      scheduleStreamReset();
    }
  }
}

async function send(): Promise<void> {
  const question = prompt.value.trim();
  await ask(question, true);
}

async function regenerateFrom(assistantIndex: number): Promise<void> {
  for (let i = assistantIndex - 1; i >= 0; i -= 1) {
    const candidate = messages.value[i];
    if (candidate.role === "user" && candidate.content.trim()) {
      syncCurrentSessionBranch();
      const session = activeSession.value;
      const current = activeBranch.value;
      const baseMessages = messages.value.slice(0, i);
      const branch = forkBranch(`${deriveTitle(candidate.content)} · retry`, baseMessages, current.id, candidate.id);
      session.branches.unshift(branch);
      session.activeBranchId = branch.id;
      loadSession(session.id);
      persistState();
      await ask(candidate.content, true);
      return;
    }
  }

  ElMessage.warning("没有找到可重试的用户问题");
}

watch(
  darkMode,
  () => {
    document.documentElement.classList.toggle("dark", darkMode.value);
    persistState();
  },
  { immediate: true }
);

watch([modelProfile, streaming, workspaceFilter, showArchivedSessions, sessionSearch], () => {
  syncCurrentSessionBranch();
  persistState();
});

watch(
  [messages, traceSteps],
  () => {
    syncCurrentSessionBranch();
    persistState();
  },
  { deep: true }
);

watch([apiKeyInput, tenantInput, token, refreshToken], () => {
  persistState();
});

watch(
  messages,
  () => {
    const idSet = new Set(messages.value.map((message) => message.id));
    const filtered: Record<string, number> = {};
    Object.entries(messageHeights.value).forEach(([id, height]) => {
      if (idSet.has(id)) {
        filtered[id] = height;
      }
    });
    messageHeights.value = filtered;
    void scrollToBottom();
  },
  { deep: false }
);

onMounted(() => {
  loadSession(activeSessionId.value);
  updateViewport();

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        const element = entry.target as HTMLElement;
        const messageId = element.dataset.msgId;
        if (!messageId) {
          return;
        }
        syncMessageHeight(messageId, Math.ceil(entry.contentRect.height));
      });
    });
  }

  window.addEventListener("resize", updateViewport);
  window.setTimeout(() => {
    hydrating.value = false;
    void scrollToBottom(true);
  }, 220);

  void scrollToBottom(true);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateViewport);

  if (resizeObserver) {
    messageRowElements.forEach((element) => {
      resizeObserver?.unobserve(element);
    });
    resizeObserver.disconnect();
    resizeObserver = null;
  }

  if (streamResetTimer) {
    window.clearTimeout(streamResetTimer);
    streamResetTimer = null;
  }
});
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  color: var(--ui-text);
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-right: 1px solid var(--ui-border);
  background: color-mix(in oklab, var(--ui-card) 88%, transparent);
  backdrop-filter: blur(12px);
}

.brand-block {
  padding: 4px 2px;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ui-muted);
}

h1 {
  margin: 8px 0 0;
  font-size: 25px;
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.brand-sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--ui-muted);
}

.new-chat-btn {
  border: 1px solid rgba(14, 116, 144, 0.35);
  background: linear-gradient(150deg, rgba(14, 116, 144, 0.2), rgba(15, 118, 110, 0.14));
  color: var(--ui-text);
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 180ms ease, box-shadow 180ms ease;
}

.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(14, 116, 144, 0.18);
}

.session-tools {
  border: 1px solid var(--ui-border);
  border-radius: 12px;
  padding: 10px;
  background: color-mix(in oklab, var(--ui-panel) 88%, transparent);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.tool-select {
  min-width: 0;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.section-label {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ui-muted);
}

.section-meta {
  font-size: 12px;
  color: var(--ui-muted);
}

.session-panel,
.branch-panel {
  border: 1px solid var(--ui-border);
  border-radius: 12px;
  padding: 10px;
  background: color-mix(in oklab, var(--ui-panel) 84%, transparent);
}

.session-list,
.branch-list {
  max-height: 214px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  border: 1px solid var(--ui-border);
  border-radius: 10px;
  padding: 8px;
  background: color-mix(in oklab, var(--ui-card) 76%, transparent);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 160ms ease;
}

.session-item:hover,
.session-item.active {
  border-color: rgba(14, 116, 144, 0.45);
}

.session-content {
  min-width: 0;
}

.session-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.session-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta-row {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ui-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.session-actions button,
.branch-head-actions button {
  border: 1px solid var(--ui-border);
  background: color-mix(in oklab, var(--ui-panel) 86%, transparent);
  color: var(--ui-text);
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.session-actions .danger {
  color: #dc2626;
}

.session-empty {
  font-size: 12px;
  color: var(--ui-muted);
  padding: 6px;
}

.branch-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.branch-item {
  position: relative;
  border: 1px solid var(--ui-border);
  border-radius: 10px;
  padding: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: color-mix(in oklab, var(--ui-card) 80%, transparent);
  cursor: pointer;
}

.branch-item.active {
  border-color: rgba(14, 116, 144, 0.45);
}

.branch-line {
  width: 10px;
  height: 1px;
  background: var(--ui-muted);
}

.branch-content {
  min-width: 0;
}

.branch-content p,
.branch-content small {
  margin: 0;
}

.branch-content p {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.branch-content small {
  color: var(--ui-muted);
}

.ops-panel {
  border: 1px solid var(--ui-border);
  border-radius: 12px;
  overflow: hidden;
  background: color-mix(in oklab, var(--ui-panel) 86%, transparent);
}

.ops-panel summary {
  list-style: none;
  cursor: pointer;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  background: color-mix(in oklab, var(--ui-card) 80%, transparent);
}

.ops-panel summary::-webkit-details-marker {
  display: none;
}

.ops-body {
  padding: 12px;
}

.auth-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.full-width {
  width: 100%;
}

.workspace {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.workspace-head {
  position: sticky;
  top: 0;
  z-index: 8;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--ui-border);
  background: color-mix(in oklab, var(--ui-card) 84%, transparent);
  backdrop-filter: blur(10px);
}

.workspace-kicker {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ui-muted);
}

h2 {
  margin: 8px 0 0;
  font-size: 22px;
  line-height: 1.22;
}

.workspace-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ui-muted);
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.workspace-select {
  width: 130px;
}

.workspace-input {
  width: 130px;
}

.stream-detail {
  font-size: 12px;
  color: var(--ui-muted);
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px 0;
}

.hydration-skeleton {
  max-width: 930px;
  margin: 0 auto;
  padding: 0 20px;
  display: grid;
  gap: 10px;
}

.skeleton-line,
.skeleton-bubble {
  border-radius: 10px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0.18), rgba(148, 163, 184, 0.34), rgba(148, 163, 184, 0.18));
  background-size: 220% 100%;
  animation: shimmer 1.3s linear infinite;
}

.skeleton-line {
  height: 12px;
}

.skeleton-line.lg {
  width: 52%;
}

.skeleton-line.short {
  width: 36%;
}

.skeleton-bubble {
  height: 84px;
}

.skeleton-bubble.alt {
  width: 76%;
  justify-self: end;
}

.welcome-block {
  max-width: 930px;
  margin: 0 auto 12px;
  padding: 0 20px;
}

.welcome-block h3 {
  margin: 0;
  font-size: 28px;
  line-height: 1.16;
}

.welcome-block p {
  margin: 8px 0 0;
  color: var(--ui-muted);
}

.welcome-prompts {
  margin-top: 14px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.welcome-prompts button,
.quick-prompts button,
.message-actions button {
  border: 1px solid var(--ui-border);
  background: color-mix(in oklab, var(--ui-panel) 88%, transparent);
  color: var(--ui-text);
  border-radius: 999px;
  padding: 6px 11px;
  font-size: 12px;
  cursor: pointer;
}

.virtual-spacer {
  width: 100%;
  pointer-events: none;
}

.message-row {
  max-width: 930px;
  margin: 0 auto;
  padding: 0 20px 18px;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
}

.message-row.user {
  grid-template-columns: minmax(0, 1fr) 38px;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  background: linear-gradient(150deg, #0f766e, #0369a1);
  color: #f8fafc;
}

.message-row.user .avatar {
  grid-column: 2;
  background: linear-gradient(150deg, #1d4ed8, #4338ca);
}

.bubble-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-row.user .bubble-wrap {
  align-items: flex-end;
}

.bubble-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--ui-muted);
  font-size: 12px;
}

.status-dot {
  color: var(--ui-accent);
}

.bubble {
  width: min(100%, 860px);
  border-radius: 14px;
  border: 1px solid var(--ui-border);
  background: color-mix(in oklab, var(--ui-card) 86%, transparent);
  padding: 12px 14px;
}

.message-row.assistant .bubble {
  border: none;
  background: transparent;
  padding: 2px 0;
}

.message-row.user .bubble {
  background: linear-gradient(150deg, rgba(29, 78, 216, 0.15), rgba(67, 56, 202, 0.12));
}

.assistant-skeleton {
  display: grid;
  gap: 8px;
}

.assistant-skeleton div {
  height: 12px;
  border-radius: 8px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0.16), rgba(148, 163, 184, 0.3), rgba(148, 163, 184, 0.16));
  background-size: 220% 100%;
  animation: shimmer 1.3s linear infinite;
}

.assistant-skeleton div:nth-child(3) {
  width: 65%;
}

.edit-box {
  display: grid;
  gap: 8px;
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.plain {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
}

.message-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.thinking {
  max-width: 930px;
  margin: 0 auto;
  padding: 0 20px 10px 70px;
  color: var(--ui-muted);
  font-size: 13px;
}

.composer-shell {
  position: sticky;
  bottom: 0;
  z-index: 6;
  padding: 0 16px 16px;
  background: linear-gradient(180deg, transparent 0%, color-mix(in oklab, var(--ui-card) 65%, transparent) 32%, color-mix(in oklab, var(--ui-card) 92%, transparent) 100%);
}

.composer {
  max-width: 930px;
  margin: 0 auto;
  border: 1px solid var(--ui-border);
  border-radius: 16px;
  background: color-mix(in oklab, var(--ui-card) 92%, transparent);
  backdrop-filter: blur(12px);
  padding: 10px;
}

.composer-footer {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.composer-actions {
  display: flex;
  gap: 8px;
}

.markdown :deep(p) {
  margin: 0 0 10px;
  line-height: 1.7;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 10px;
  padding-left: 20px;
}

.markdown :deep(code:not(.hljs)) {
  font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
  background: rgba(15, 23, 42, 0.1);
  border-radius: 4px;
  padding: 2px 5px;
}

.markdown :deep(.code-block) {
  border: 1px solid var(--ui-border);
  border-radius: 12px;
  overflow: hidden;
  background: #0b1220;
  color: #e6edf7;
}

.markdown :deep(.code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: #111b2f;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.markdown :deep(.code-lang) {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #9fb2cf;
}

.markdown :deep(.copy-code-btn) {
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 11px;
  background: rgba(15, 23, 42, 0.5);
  color: #e6edf7;
  cursor: pointer;
}

.markdown :deep(pre) {
  margin: 0;
  padding: 0;
  overflow-x: auto;
}

.markdown :deep(code.hljs) {
  display: block;
  padding: 10px 0;
  background: transparent;
  font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.markdown :deep(.code-line) {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 10px;
  padding: 0 12px;
  white-space: pre;
}

.markdown :deep(.line-no) {
  user-select: none;
  color: rgba(148, 163, 184, 0.7);
  text-align: right;
}

.markdown :deep(.line-content) {
  min-width: 0;
}

.markdown :deep(.hljs-comment),
.markdown :deep(.hljs-quote) {
  color: #8aa0bf;
}

.markdown :deep(.hljs-keyword),
.markdown :deep(.hljs-selector-tag),
.markdown :deep(.hljs-subst) {
  color: #ff8fa3;
}

.markdown :deep(.hljs-string),
.markdown :deep(.hljs-doctag) {
  color: #8be9a8;
}

.markdown :deep(.hljs-title),
.markdown :deep(.hljs-section),
.markdown :deep(.hljs-selector-id) {
  color: #8fc7ff;
}

.markdown :deep(.hljs-number),
.markdown :deep(.hljs-literal) {
  color: #f6c177;
}

:deep(.composer .el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  font-size: 15px;
  line-height: 1.58;
  color: var(--ui-text);
}

:deep(.composer .el-textarea__inner:focus) {
  box-shadow: none;
}

@keyframes shimmer {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: -120% 0;
  }
}

@media (max-width: 1160px) {
  .app-shell {
    grid-template-columns: 300px minmax(0, 1fr);
  }
}

@media (max-width: 980px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: none;
    border-bottom: 1px solid var(--ui-border);
  }

  .session-list,
  .branch-list {
    max-height: 170px;
  }

  .workspace-head {
    position: static;
  }

  .composer-shell {
    position: static;
  }
}

@media (max-width: 680px) {
  .workspace-head {
    padding-left: 12px;
    padding-right: 12px;
  }

  .head-actions {
    justify-content: flex-start;
  }

  .workspace-select,
  .workspace-input {
    width: 120px;
  }

  .welcome-block,
  .message-row,
  .thinking,
  .hydration-skeleton {
    padding-left: 12px;
    padding-right: 12px;
  }

  .message-row {
    grid-template-columns: 32px minmax(0, 1fr);
    gap: 8px;
  }

  .message-row.user {
    grid-template-columns: minmax(0, 1fr) 32px;
  }

  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 8px;
  }

  .thinking {
    padding-left: 52px;
  }

  .composer-footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
