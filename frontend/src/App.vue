<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">AI Console</p>
        <h1>ReAct Assistant Workbench</h1>
        <p class="subtext">Thought → Action → Observation 可视化，面向企业演示与联调。</p>
      </div>
      <div class="topbar-actions">
        <el-switch
          v-model="darkMode"
          inline-prompt
          active-text="Dark"
          inactive-text="Light"
        />
      </div>
    </header>

    <main class="layout">
      <aside class="left-pane">
        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-title">鉴权</div>
          </template>
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
          </el-form>
          <div class="auth-buttons">
            <el-button type="primary" :loading="authLoading" @click="handleLogin">换取 JWT</el-button>
            <el-button :disabled="!refreshToken" :loading="refreshing" @click="handleRefresh">刷新令牌</el-button>
            <el-button @click="clearAuth">清空</el-button>
          </div>
          <div class="auth-status">
            <el-tag :type="token ? 'success' : 'warning'" effect="plain">
              {{ token ? "JWT 已就绪" : "未登录（可直接 API Key 调用）" }}
            </el-tag>
            <el-tag v-if="tenantInput" type="info" effect="plain">{{ tenantInput }}</el-tag>
          </div>
        </el-card>

        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-title">会话参数</div>
          </template>
          <el-form label-position="top" size="small">
            <el-form-item label="Chat ID">
              <el-input v-model="chatId" />
            </el-form-item>
            <el-form-item label="Model Profile">
              <el-select v-model="modelProfile" class="full-width">
                <el-option label="economy" value="economy" />
                <el-option label="balanced" value="balanced" />
                <el-option label="quality" value="quality" />
              </el-select>
            </el-form-item>
            <el-form-item label="输出方式">
              <el-switch
                v-model="streaming"
                inline-prompt
                active-text="SSE"
                inactive-text="JSON"
              />
            </el-form-item>
          </el-form>
          <div class="session-actions">
            <el-button @click="newSession">新会话</el-button>
            <el-button :disabled="sending" @click="clearConversation">清空对话</el-button>
          </div>
        </el-card>

        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-title">ReAct 轨迹</div>
          </template>
          <div class="trace-list">
            <div v-if="traceSteps.length === 0" class="trace-empty">发送问题后将展示推理轨迹。</div>
            <div v-for="trace in traceSteps" :key="trace.step" class="trace-step">
              <div class="trace-step-head">
                <span class="trace-index">#{{ trace.step }}</span>
                <el-tag size="small" type="success">{{ trace.action }}</el-tag>
              </div>
              <p class="trace-thought">{{ trace.thought || "无显式 thought" }}</p>
              <details class="trace-raw">
                <summary>查看 action_input / observation</summary>
                <pre>{{ stringify(trace.actionInput) }}</pre>
                <pre>{{ stringify(trace.observation) }}</pre>
              </details>
            </div>
          </div>
        </el-card>
      </aside>

      <section class="chat-pane">
        <el-card class="chat-card" shadow="never">
          <template #header>
            <div class="panel-title">ReAct 对话</div>
          </template>
          <div ref="messageContainer" class="messages">
            <article
              v-for="item in messages"
              :key="item.id"
              class="message-row"
              :class="item.role"
            >
              <div class="avatar">{{ item.role === "user" ? "U" : "AI" }}</div>
              <div class="bubble">
                <div v-if="item.role === 'assistant'" class="markdown" v-html="renderMarkdown(item.content)" />
                <p v-else class="plain">{{ item.content }}</p>
              </div>
            </article>
          </div>

          <div class="composer">
            <el-input
              v-model="prompt"
              class="composer-input"
              type="textarea"
              :rows="3"
              resize="none"
              placeholder="输入问题，按 Enter 发送（Shift + Enter 换行）"
              @keydown.enter.exact.prevent="send"
            />
            <div class="composer-footer">
              <div class="quick-prompts">
                <el-button
                  v-for="sample in quickPrompts"
                  :key="sample"
                  size="small"
                  text
                  @click="prompt = sample"
                >
                  {{ sample }}
                </el-button>
              </div>
              <el-button type="primary" :loading="sending" @click="send">发送</el-button>
            </div>
          </div>
        </el-card>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from "dompurify";
import { ElMessage } from "element-plus";
import { marked } from "marked";
import { nextTick, onMounted, ref, watch } from "vue";
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
}

const STORAGE_KEY = "knowledgeops-agent-react-console";

marked.setOptions({
  gfm: true,
  breaks: true
});

function createChatId(): string {
  const suffix = Math.random().toString(36).slice(2, 8);
  return `react-${Date.now()}-${suffix}`;
}

function createMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content
  };
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
  return DOMPurify.sanitize(html);
}

const cachedRaw = localStorage.getItem(STORAGE_KEY);
const cached = cachedRaw ? JSON.parse(cachedRaw) as Record<string, string | boolean> : {};

const darkMode = ref(Boolean(cached.darkMode));
const apiKeyInput = ref((cached.apiKey as string | undefined) ?? "");
const tenantInput = ref((cached.tenantId as string | undefined) ?? "");
const token = ref((cached.token as string | undefined) ?? "");
const refreshToken = ref((cached.refreshToken as string | undefined) ?? "");
const chatId = ref((cached.chatId as string | undefined) ?? createChatId());
const modelProfile = ref((cached.modelProfile as string | undefined) ?? "balanced");
const streaming = ref((cached.streaming as boolean | undefined) ?? true);

const authLoading = ref(false);
const refreshing = ref(false);
const sending = ref(false);
const prompt = ref("");
const traceSteps = ref<ReactTraceStep[]>([]);
const messageContainer = ref<HTMLElement | null>(null);

const quickPrompts = [
  "帮我按课程类型推荐三门就业导向课程",
  "先检索知识库，再给出本周学习计划",
  "我想预约课程，告诉我需要哪些字段"
];

const messages = ref<ChatMessage[]>([
  createMessage(
    "assistant",
    "欢迎使用 ReAct 控制台。你可以先输入 API Key 获取 JWT，然后发起带轨迹的问答。"
  )
]);

function persistState(): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      darkMode: darkMode.value,
      apiKey: apiKeyInput.value,
      tenantId: tenantInput.value,
      token: token.value,
      refreshToken: refreshToken.value,
      chatId: chatId.value,
      modelProfile: modelProfile.value,
      streaming: streaming.value
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

function upsertTrace(step: ReactTraceStep): void {
  const index = traceSteps.value.findIndex((item) => item.step === step.step);
  if (index >= 0) {
    traceSteps.value[index] = step;
  } else {
    traceSteps.value.push(step);
    traceSteps.value.sort((a, b) => a.step - b.step);
  }
}

async function scrollToBottom(): Promise<void> {
  await nextTick();
  const element = messageContainer.value;
  if (!element) {
    return;
  }
  element.scrollTop = element.scrollHeight;
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

function newSession(): void {
  chatId.value = createChatId();
  clearConversation();
  persistState();
}

function clearConversation(): void {
  messages.value = [
    createMessage(
      "assistant",
      "会话已重置。你可以继续发问，系统会重新生成 ReAct 轨迹。"
    )
  ];
  traceSteps.value = [];
}

async function send(): Promise<void> {
  const question = prompt.value.trim();
  if (!question || sending.value) {
    return;
  }

  const userMsg = createMessage("user", question);
  const assistantMsg = createMessage("assistant", "");
  messages.value.push(userMsg, assistantMsg);
  const assistantIndex = messages.value.length - 1;
  traceSteps.value = [];
  prompt.value = "";
  sending.value = true;
  await scrollToBottom();

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
            upsertTrace(payload as ReactTraceStep);
            return;
          }
          if (event === "token") {
            const tokenEvent = payload as ReactTokenEvent;
            messages.value[assistantIndex].content += tokenEvent.token ?? "";
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
            return;
          }
          if (event === "error") {
            const err = payload as ReactErrorEvent;
            streamError = err.message || "stream error";
          }
        }
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
        authContext()
      );
      traceSteps.value = result.trace ?? [];
      messages.value[assistantIndex].content = result.answer || "模型没有返回内容";
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "request failed";
    messages.value[assistantIndex].content = `请求失败：${message}`;
    ElMessage.error(message);
  } finally {
    sending.value = false;
    persistState();
    await scrollToBottom();
  }
}

watch(
  [darkMode, modelProfile, streaming, chatId, apiKeyInput, tenantInput],
  () => {
    document.documentElement.classList.toggle("dark", darkMode.value);
    persistState();
  },
  { immediate: true }
);

onMounted(() => {
  void scrollToBottom();
});
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  color: var(--ui-text);
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px;
}

.eyebrow {
  margin: 0 0 4px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-size: 12px;
  color: var(--ui-muted);
}

h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.15;
  font-weight: 700;
}

.subtext {
  margin: 8px 0 0;
  color: var(--ui-muted);
}

.layout {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 18px;
  padding: 0 24px 24px;
}

.left-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel {
  border-radius: 18px;
  border: 1px solid var(--ui-border);
  background: var(--ui-card);
  backdrop-filter: blur(10px);
}

.panel-title {
  font-weight: 600;
}

.auth-buttons,
.session-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.auth-status {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.full-width {
  width: 100%;
}

.trace-list {
  max-height: 340px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-empty {
  color: var(--ui-muted);
  font-size: 13px;
}

.trace-step {
  border: 1px solid var(--ui-border);
  border-radius: 12px;
  padding: 10px;
  background: var(--ui-panel);
}

.trace-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.trace-index {
  font-size: 12px;
  color: var(--ui-muted);
}

.trace-thought {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}

.trace-raw {
  margin-top: 8px;
}

.trace-raw summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--ui-accent);
}

.trace-raw pre {
  margin: 8px 0 0;
  padding: 8px;
  border-radius: 8px;
  font-size: 12px;
  background: rgba(15, 23, 42, 0.08);
  overflow-x: auto;
}

.chat-pane {
  min-height: 0;
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 20px;
  border: 1px solid var(--ui-border);
  background: var(--ui-card);
}

:deep(.chat-card .el-card__body) {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.messages {
  flex: 1;
  min-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-right: 4px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
  font-size: 12px;
  font-weight: 700;
  background: linear-gradient(160deg, #0f766e, #0369a1);
  color: #f8fafc;
}

.message-row.user .avatar {
  background: linear-gradient(160deg, #1d4ed8, #4338ca);
}

.bubble {
  max-width: min(85%, 840px);
  padding: 12px 14px;
  border-radius: 14px;
  line-height: 1.58;
  border: 1px solid var(--ui-border);
  background: var(--ui-panel);
}

.message-row.user .bubble {
  background: linear-gradient(150deg, rgba(29, 78, 216, 0.14), rgba(67, 56, 202, 0.12));
}

.plain {
  margin: 0;
  white-space: pre-wrap;
}

.composer {
  border-top: 1px solid var(--ui-border);
  padding-top: 12px;
}

.composer-footer {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.markdown :deep(p) {
  margin: 0 0 8px;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(code) {
  font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
  background: rgba(15, 23, 42, 0.1);
  border-radius: 4px;
  padding: 2px 4px;
}

.markdown :deep(pre) {
  margin: 10px 0;
  padding: 12px;
  border-radius: 10px;
  overflow-x: auto;
  background: rgba(15, 23, 42, 0.12);
}

@media (max-width: 1080px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .messages {
    min-height: 260px;
  }
}

@media (max-width: 680px) {
  .topbar,
  .layout {
    padding-left: 12px;
    padding-right: 12px;
  }

  h1 {
    font-size: 24px;
  }
}
</style>
