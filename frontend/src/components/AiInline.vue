<template>
  <el-card class="ai-inline" shadow="never">
    <div class="aii-head" @click="open = !open">
      <span class="aii-dot"></span>
      <span class="aii-title">AI 助手 · {{ context }}</span>
      <span class="aii-hint">{{ open ? '它知道你正在这个页面' : '点开展开对话' }}</span>
      <span class="aii-toggle">{{ open ? '收起 ▾' : '展开 ▴' }}</span>
    </div>

    <div v-show="open" ref="bodyEl" class="aii-body">
      <div v-if="!recent.length" class="aii-empty">
        直接用一句话让它干活，例如「{{ placeholderByContext }}」——它能读写这个软件的数据，答题、出题的数据都会正常入库。
      </div>
      <div v-for="(m, i) in recent" :key="i" :class="['aii-msg', m.role]">
        <AiTrace
          v-if="m.trace && m.trace.length"
          compact
          :trace="m.trace" :pending="!!m.pending"
          :elapsed-ms="m.elapsedMs || 0" :start-at="m.startAt || 0"
        />
        <div v-else-if="m.steps && m.steps.length" class="aii-steps">
          <span
            v-for="(s, j) in m.steps" :key="j"
            :class="['aii-step', { fail: s.ok === false, write: s.write }]"
          >{{ toolLabel(s.tool) }}</span>
        </div>
        <div v-if="m.content" class="aii-bubble" v-html="renderMd(m.content)"></div>
        <div v-if="m.pending" class="aii-bubble thinking"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
      </div>
    </div>

    <div class="aii-input">
      <el-input
        v-model="draft"
        :placeholder="placeholderByContext"
        size="default"
        @keydown.enter.exact.prevent="sendNow"
      />
      <el-button v-if="busy" @click="stop">停止</el-button>
      <el-button type="primary" :loading="busy" :disabled="!draft.trim()" @click="sendNow">发送</el-button>
    </div>
  </el-card>
</template>

<script setup>
// 页面内嵌 AI：每个功能页底部都有一个，带着本页上下文对话。
// 与浮窗/主对话页共用同一份会话历史与联动逻辑（useAiConversation）。
import { ref, computed, watch, nextTick } from 'vue'
import { useAiConversation, toolLabel } from '../composables/useAiConversation'
import AiTrace from './AiTrace.vue'

const props = defineProps({
  context: { type: String, required: true }, // 如「自测」「复习任务」
  hint: { type: String, default: '' },       // 输入框 placeholder 的场景提示
})

const STORE_MSGS = 'lp_ai_chat_msgs'
const STORE_PREFS = 'lp_ai_chat_prefs'

const PLACEHOLDER = {
  自测: '让 AI 出几道题马上开做，或讲讲这道题为什么错…',
  错题本: '让 AI 诊断错因、给改法，或按错因出几道巩固题…',
  复习任务: '让 AI 排复习计划，或调整/解释现有任务…',
  史实要点: '让 AI 补充/讲解某个要点，或考考你这里面的内容…',
  教材目录: '让 AI 讲某一章的脉络，或把某节整理成要点…',
  四史时间轴: '让 AI 补事件、讲某段时期的前因后果…',
  史料笔记: '让 AI 把资料整理成知识点、或基于资料出题…',
  学习看板: '让 AI 看看你的学习数据，安排今天怎么学…',
}

const msgs = ref(loadMsgs())
const draft = ref('')
const busy = ref(false)
const controller = ref(null)
const open = ref(true)
const bodyEl = ref(null)

const prefs = loadPrefs()

const conv = useAiConversation({
  msgs,
  busy,
  controller,
  persist,
  getAllowWrite: () => prefs.allowWrite !== false,
  getUiLink: () => prefs.uiLink !== false,
  // 关键：告诉后端「学生此刻在哪个功能页」，AI 才能贴着当前场景回答
  getPageContext: () => props.context,
  onNavigated: (target) => { if (target) open.value = false }, // 跳走了就收起，别跟着新页面乱飘
})

// 只显示最近 8 条，保持页面轻量
const recent = computed(() => msgs.value.slice(-8))

const placeholderByContext = computed(() => props.hint || PLACEHOLDER[props.context] || `在这个页面你想让 AI 做什么？`)

function sendNow() {
  const t = draft.value.trim()
  if (!t || busy.value) return
  draft.value = ''
  conv.send(t)
}

function stop() {
  conv.stop()
}

function loadMsgs() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_MSGS) || '[]')
    return Array.isArray(raw) ? raw.filter((m) => !m.pending) : []
  } catch {
    return []
  }
}

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(STORE_PREFS) || '{}') } catch { return {} }
}

function persist() {
  const clean = msgs.value.filter((m) => !m.pending).slice(-40)
  localStorage.setItem(STORE_MSGS, JSON.stringify(clean))
}

// 极简 Markdown：转义后只处理加粗/行内代码/换行（模型输出不可信）
function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function renderMd(text) {
  if (!text) return ''
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .split('\n').map((l) => l.trim() ? `<p>${l}</p>` : '').join('')
}

watch(msgs, () => nextTick(() => {
  if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight
}), { deep: true })
</script>

<style scoped>
.ai-inline { margin-top: 14px; border: 1px dashed #b3d8ff; background: #f7fbff; }
.aii-head { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.aii-dot { width: 8px; height: 8px; border-radius: 50%; background: #409eff; box-shadow: 0 0 0 3px rgba(64, 158, 255, .15); }
.aii-title { font-weight: 700; }
.aii-hint { color: #909399; font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aii-toggle { color: #409eff; font-size: 12px; }
.aii-body { max-height: 280px; overflow-y: auto; margin-top: 10px; padding: 4px 2px; }
.aii-empty { color: #909399; font-size: 13px; line-height: 1.7; padding: 6px 2px; }
.aii-msg { margin-bottom: 10px; }
.aii-msg.user .aii-bubble { background: #ecf5ff; border-radius: 8px; padding: 6px 10px; display: inline-block; }
.aii-steps { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.aii-step { font-size: 11px; color: #909399; background: #f0f2f5; border-radius: 4px; padding: 1px 6px; }
.aii-step.write { color: #e6a23c; background: #fdf6ec; }
.aii-step.fail { color: #f56c6c; background: #fef0f0; }
.aii-bubble { font-size: 13.5px; line-height: 1.7; }
.aii-bubble :deep(p) { margin: 2px 0; }
.aii-bubble :deep(code) { background: #f0f2f5; padding: 0 4px; border-radius: 3px; }
.aii-bubble.thinking { display: inline-flex; gap: 4px; align-items: center; }
.dot { width: 5px; height: 5px; border-radius: 50%; background: #409eff; display: inline-block; animation: aiiBlink 1.2s infinite; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes aiiBlink { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }
.aii-input { display: flex; gap: 8px; margin-top: 10px; }
.aii-input .el-input { flex: 1; }
@media (max-width: 768px) {
  .aii-hint { display: none; }
  .aii-body { max-height: 220px; }
}
</style>
