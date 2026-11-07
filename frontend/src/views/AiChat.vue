<template>
  <div class="chat-wrap">
    <header class="chat-head">
      <div class="head-left">
        <span class="title">AI 学习管家</span>
        <el-tag size="small" effect="plain" :style="{ borderColor: trackColor, color: trackColor }">
          {{ trackName || '未选课' }}
        </el-tag>
        <el-tag v-if="aiSource === 'builtin'" size="small" type="success" effect="plain">内置阶跃</el-tag>
        <el-tag v-else-if="aiSource === 'custom'" size="small" type="success" effect="plain">自建模型</el-tag>
        <el-tag v-else size="small" type="warning" effect="plain">未配置 Key</el-tag>
      </div>
      <div class="head-right">
        <span class="switch-label">允许 AI 写入</span>
        <el-switch v-model="allowWrite" size="small" @change="savePrefs" />
        <span class="switch-label">联动跳转</span>
        <el-switch v-model="uiLink" size="small" @change="savePrefs" />
        <el-button size="small" @click="openTools">能做什么</el-button>
        <el-button size="small" @click="openConfig">AI 设置</el-button>
        <el-button size="small" type="primary" plain @click="newChat">新对话</el-button>
      </div>
    </header>

    <div ref="scrollEl" class="chat-body">
      <div v-if="!msgs.length" class="welcome">
        <div class="welcome-title">让 AI 把这一门课陪你学完</div>
        <p class="welcome-sub">
          它不只是聊天：能查教材目录、翻史料原文、建史实要点、生成资料入库、出题、排复习任务。
          说一句「帮我学第三章」，它会把整套动作自己跑完。
        </p>
        <div class="quick-grid">
          <div v-for="q in quickPrompts" :key="q" class="quick-card" @click="send(q)">{{ q }}</div>
        </div>
      </div>

      <div v-for="(m, i) in msgs" :key="i" :class="['row', m.role]">
        <div class="avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
        <div class="bubble-col">
          <div v-if="m.steps && m.steps.length" class="steps">
            <div v-for="(s, j) in m.steps" :key="j" class="step" :class="{ fail: s.ok === false, write: s.write }">
              <span class="step-name">{{ toolLabel(s.tool) }}</span>
              <span class="step-sum">{{ s.summary || '执行中…' }}</span>
            </div>
          </div>
          <div v-if="m.content" class="bubble" v-html="renderMd(m.content)"></div>
          <div v-if="m.pending" class="bubble thinking">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>
    </div>

    <footer class="chat-foot">
      <div v-if="voice.state.value === 'listening'" class="voice-tip">
        <span class="rec-dot"></span>
        {{ voice.mode.value === 'web' ? '正在听你说…（再点麦克风结束）' : '正在录音…（再点麦克风结束）' }}
      </div>
      <div v-else-if="voice.state.value === 'processing'" class="voice-tip processing">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        正在转成文字…
      </div>
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        resize="none"
        placeholder="问史实、让 AI 整理知识点、出题、排复习计划…（Enter 发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send()"
      />
      <div class="foot-actions">
        <span class="foot-hint">AI 会真实读写软件数据，写入的动作在上面以卡片显示</span>
        <el-tooltip :content="micTip" placement="top">
          <el-button
            class="mic-btn"
            :class="{ recording: voice.state.value === 'listening' }"
            circle
            :type="voice.state.value === 'listening' ? 'danger' : 'default'"
            :disabled="busy"
            @click="toggleMic"
          >
            <el-icon :size="17"><Microphone /></el-icon>
          </el-button>
        </el-tooltip>
        <el-button v-if="busy" @click="stop">停止</el-button>
        <el-button type="primary" :loading="busy" :disabled="!draft.trim()" @click="send()">发送</el-button>
      </div>
    </footer>

    <!-- 工具能力 -->
    <el-dialog v-model="toolsVisible" title="AI 在这个软件里能做什么" width="620px" append-to-body>
      <p class="muted" style="margin-top:0">
        只读工具任何时候都可用；写入工具受上方「允许 AI 写入」开关控制。AI 没有任何删除权限。
        开着「联动跳转」时，说「切到史料笔记」AI 会直接帮你切页面，出完题也会自动跳到自测。
      </p>
      <el-table :data="tools" size="small" max-height="420">
        <el-table-column prop="name" label="工具" width="190" />
        <el-table-column label="权限" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.write ? 'warning' : 'info'" effect="plain">
              {{ row.write ? '写入' : '只读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="作用" />
      </el-table>
    </el-dialog>

    <!-- AI 配置 -->
    <el-dialog v-model="configVisible" title="配置 AI 大模型" width="560px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="默认内置阶跃 StepFun，不填也能用"
        description="想换成自己的模型：选平台预设 → 粘贴 Key → 保存。境外平台（如 Gemini）才需要填代理。"
        style="margin-bottom:14px"
      />
      <el-form label-width="90px">
        <el-form-item label="平台预设">
          <el-select v-model="config.preset" style="width:100%" @change="applyPreset">
            <el-option label="阶跃 StepFun（内置默认，国内直连）" value="stepfun" />
            <el-option label="智谱 GLM（国内直连，永久免费）" value="zhipu" />
            <el-option label="MiniMax M Plan（订阅 Key）" value="minimax" />
            <el-option label="硅基流动 SiliconFlow" value="siliconflow" />
            <el-option label="阿里云百炼 DashScope" value="dashscope" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="OpenRouter" value="openrouter" />
            <el-option label="Google Gemini（境外，需代理）" value="gemini" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="config.api_key" show-password placeholder="粘贴自己的 Key；留空保存＝恢复内置阶跃" />
        </el-form-item>
        <el-form-item label="接口地址"><el-input v-model="config.base_url" /></el-form-item>
        <el-form-item label="模型名"><el-input v-model="config.model" /></el-form-item>
        <el-form-item label="代理地址">
          <el-input v-model="config.proxy" placeholder="可留空；境内访问 Google 填 http://127.0.0.1:7897" />
        </el-form-item>
        <el-form-item label="配置文件"><span class="muted">{{ config.env_path || '程序目录下的 .env' }}</span></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button @click="resetAi" :loading="saveLoading">恢复默认</el-button>
        <el-button type="primary" :loading="saveLoading" @click="saveAi">保存并生效</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { Microphone } from '@element-plus/icons-vue'
import { useVoiceInput } from '../composables/voice'
import { useAiConversation, toolLabel } from '../composables/useAiConversation'
import api, { auth } from '../api'

const route = useRoute()
const router = useRouter()

const TRACKS = {
  party: { name: '党史', color: '#c0392b' },
  prc: { name: '新中国史', color: '#c47f17' },
  reform: { name: '改革开放史', color: '#1d7a4f' },
  socialism: { name: '社会主义发展史', color: '#3b5b9a' },
}
const STORE_MSGS = 'lp_ai_chat_msgs'
const STORE_PREFS = 'lp_ai_chat_prefs'

const emit = defineEmits(['navigated'])

const trackName = computed(() => TRACKS[auth.track()]?.name || '')
const trackColor = computed(() => TRACKS[auth.track()]?.color || '#909399')

const msgs = ref(loadMsgs())
const draft = ref('')
const busy = ref(false)

// ---------- 语音输入：说话 → 填进输入框（可改可删，再自己点发送）----------
const voiceBase = ref('') // 开始录音前输入框里已有的内容，识别结果接在后面
const voice = useVoiceInput({
  onText: (text, { final }) => {
    draft.value = (voiceBase.value + (final ? text : ' ' + text)).trimStart()
    if (final) voiceBase.value = ''
  },
})
const micTip = computed(() => {
  if (voice.state.value === 'listening') return '点击麦克风结束输入'
  if (voice.state.value === 'processing') return '正在转成文字…'
  return voice.mode.value === 'web'
    ? '语音输入（浏览器实时识别）'
    : '语音输入（录完由服务端识别）'
})
function toggleMic() {
  if (voice.state.value === 'idle') {
    voiceBase.value = draft.value ? draft.value + ' ' : ''
    nextTick(() => document.querySelector('.mic-btn')?.blur())
  }
  voice.toggle()
}
const allowWrite = ref(loadPrefs().allowWrite !== false)
const uiLink = ref(loadPrefs().uiLink !== false)
const aiSource = ref('none')
const scrollEl = ref(null)
const toolsVisible = ref(false)
const tools = ref([])
const controller = ref(null)

// 对话核心逻辑在 useAiConversation（与各页面内嵌 AI 共用）
const conv = useAiConversation({
  msgs,
  busy,
  controller,
  persist,
  getAllowWrite: () => allowWrite.value,
  getUiLink: () => uiLink.value,
  onNavigated: (t) => emit('navigated', t),
})

function send(text) {
  const raw = (text ?? draft.value).trim()
  if (!raw || busy.value) return
  draft.value = ''
  conv.send(raw)
}

function stop() {
  conv.stop()
}

const quickPrompts = [
  '帮我看看这门课第一章讲什么，给我建 3 条史实要点',
  '把这一章的核心内容整理成一篇资料存进史料笔记',
  '根据我已有的知识点出 5 道题，覆盖单选和材料分析',
  '我最近哪里薄弱？给我排一周的复习任务',
  '讲一下我错题本里错得最多的那个考点',
  '帮我看看错题为什么老错，把错因标出来并给改法',
]

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
function savePrefs() {
  localStorage.setItem(STORE_PREFS, JSON.stringify({ allowWrite: allowWrite.value, uiLink: uiLink.value }))
}
function persist() {
  const clean = msgs.value.filter((m) => !m.pending).slice(-40)
  localStorage.setItem(STORE_MSGS, JSON.stringify(clean))
}

// toolLabel 已从 useAiConversation 导入
// 极简 Markdown：只处理标题/加粗/列表/代码，先转义再加标签（模型输出不可信）
function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inline(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}
function renderMd(text) {
  if (!text) return ''
  const lines = escapeHtml(text).split('\n')
  const out = []
  let list = null
  const closeList = () => {
    if (list) { out.push(`</${list}>`); list = null }
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) { closeList(); continue }
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) { closeList(); out.push(`<div class="md-h${h[1].length}">${inline(h[2])}</div>`); continue }
    const ul = line.match(/^\s*[-*•]\s+(.*)$/)
    if (ul) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul' }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (ol) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol' }
      out.push(`<li>${inline(ol[1])}</li>`)
      continue
    }
    closeList()
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  return out.join('')
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}
watch(msgs, scrollToBottom, { deep: true })

function newChat() {
  if (busy.value) return ElMessage.warning('等这轮回答结束再开新对话')
  msgs.value = []
  persist()
}


// ---- AI 状态与配置 ----
async function loadStatus() {
  try {
    const h = await api.aiHealth()
    aiSource.value = h.ai_source || (h.ai_available ? 'custom' : 'none')
  } catch { /* 忽略 */ }
}

const configVisible = ref(false)
const saveLoading = ref(false)
const presets = ref({})
const config = ref({ preset: 'stepfun', api_key: '', base_url: '', model: '', proxy: '', env_path: '' })

async function openConfig() {
  try {
    const c = await api.aiConfig()
    presets.value = c.presets || {}
    config.value = {
      preset: 'stepfun',
      api_key: '',
      base_url: c.base_url,
      model: c.model,
      proxy: c.proxy || '',
      env_path: c.env_path,
    }
    configVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}
function applyPreset(name) {
  const p = presets.value[name]
  if (p) {
    config.value.base_url = p.base_url
    config.value.model = p.model
  }
}
async function saveAi() {
  saveLoading.value = true
  try {
    const r = await api.saveAiConfig({
      api_key: config.value.api_key.trim(),
      base_url: config.value.base_url,
      model: config.value.model,
      proxy: config.value.proxy,
    })
    ElMessage.success(r.message)
    configVisible.value = false
    config.value.api_key = ''
    await loadStatus()
    const t = await api.aiTest()
    ElMessage[t.ok ? 'success' : 'warning'](t.message)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}
async function resetAi() {
  saveLoading.value = true
  try {
    const r = await api.saveAiConfig({ api_key: '', base_url: '', model: '', proxy: '' })
    ElMessage.success(r.message)
    configVisible.value = false
    await loadStatus()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}

async function openTools() {
  toolsVisible.value = true
  if (tools.value.length) return
  try {
    const r = await api.aiTools()
    tools.value = r.tools || []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await loadStatus()
  // 从错题本/仪表盘带问题跳过来时（/ai?q=...）直接替他发出去，少点一次
  const q = typeof route.query.q === 'string' ? route.query.q.trim() : ''
  if (q) {
    draft.value = q
    await send(q)
  }
})
</script>

<style scoped>
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
  height: calc(100dvh - 40px); /* 手机地址栏伸缩时用 dvh，避免输入框被顶出屏幕 */
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  overflow: hidden;
}
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  flex-wrap: wrap;
}
.head-left { display: flex; align-items: center; gap: 8px; }
.title { font-weight: 700; font-size: 15px; color: #303133; }
.head-right { display: flex; align-items: center; gap: 8px; }
.switch-label { font-size: 12px; color: #909399; }

.chat-body { flex: 1; overflow-y: auto; padding: 18px 20px; background: #fafbfc; }
.welcome { max-width: 720px; margin: 24px auto; }
.welcome-title { font-size: 19px; font-weight: 700; color: #303133; margin-bottom: 8px; }
.welcome-sub { font-size: 13px; line-height: 1.8; color: #606266; margin: 0 0 18px; }
.quick-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.quick-card {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 13px;
  color: #303133;
  background: #fff;
  cursor: pointer;
  line-height: 1.6;
  transition: all 0.15s;
}
.quick-card:hover { border-color: #409eff; color: #409eff; background: #f2f8ff; }

.row { display: flex; gap: 10px; margin-bottom: 18px; }
.row.user { flex-direction: row-reverse; }
.avatar {
  width: 30px; height: 30px; flex: 0 0 30px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #fff; background: #a8b3c4;
}
.row.user .avatar { background: #409eff; }
.bubble-col { max-width: min(78%, 760px); display: flex; flex-direction: column; gap: 6px; }
.row.user .bubble-col { align-items: flex-end; }
.bubble {
  background: #fff; border: 1px solid #ebeef5; border-radius: 10px;
  padding: 12px 14px; font-size: 13.5px; line-height: 1.8; color: #303133;
  word-break: break-word;
}
.row.user .bubble { background: #ecf5ff; border-color: #d9ecff; }
.bubble :deep(p) { margin: 0 0 6px; }
.bubble :deep(p:last-child) { margin-bottom: 0; }
.bubble :deep(ul), .bubble :deep(ol) { margin: 4px 0 8px; padding-left: 20px; }
.bubble :deep(code) { background: #f4f4f5; padding: 1px 4px; border-radius: 3px; font-size: 12.5px; }
.bubble :deep(.md-h1), .bubble :deep(.md-h2), .bubble :deep(.md-h3), .bubble :deep(.md-h4) {
  font-weight: 700; margin: 10px 0 6px;
}
.bubble :deep(.md-h1) { font-size: 16px; }
.bubble :deep(.md-h2) { font-size: 15px; }
.bubble :deep(.md-h3), .bubble :deep(.md-h4) { font-size: 14px; }

.steps { display: flex; flex-direction: column; gap: 4px; }
.step {
  display: flex; align-items: baseline; gap: 8px; font-size: 12px;
  background: #f4f6f9; border: 1px solid #e9edf3; border-radius: 6px;
  padding: 5px 9px; color: #606266;
}
.step.write { background: #fdf6ec; border-color: #faecd8; }
.step.fail { background: #fef0f0; border-color: #fde2e2; color: #c45656; }
.step-name { font-weight: 600; color: #303133; flex: 0 0 auto; }
.step-sum { color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.thinking { display: flex; align-items: center; gap: 5px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: #b1b7c2; animation: blink 1.2s infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.25 } 40% { opacity: 1 } }

.chat-foot { border-top: 1px solid #ebeef5; padding: 10px 14px 12px; background: #fff; }
.foot-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.foot-hint { margin-right: auto; font-size: 12px; color: #b1b7c2; }
.muted { color: #909399; font-size: 13px; }

/* 语音输入 */
.voice-tip {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #e24b4a; margin-bottom: 6px;
}
.voice-tip.processing { color: #185fa5; }
.rec-dot {
  width: 9px; height: 9px; border-radius: 50%; background: #e24b4a;
  animation: rec-blink 1s ease-in-out infinite;
}
@keyframes rec-blink { 50% { opacity: 0.25; } }
.mic-btn.recording { animation: mic-pulse 1.2s ease-in-out infinite; }
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(226, 75, 74, 0.45); }
  50% { box-shadow: 0 0 0 7px rgba(226, 75, 74, 0.12); }
}

/* 手机/竖屏平板：顶栏按钮换行、气泡更宽、快捷指令单列，输入区贴底 */
@media (max-width: 768px) {
  .chat-wrap {
    height: calc(100dvh - 68px);
    border-radius: 0;
    border-left: none;
    border-right: none;
  }
  .chat-head { padding: 8px 10px; gap: 6px; }
  .head-left .title { font-size: 14px; }
  .head-right { width: 100%; justify-content: flex-end; flex-wrap: wrap; }
  .chat-body { padding: 12px 10px; }
  .bubble-col { max-width: 88%; }
  .bubble { padding: 10px 12px; font-size: 13px; }
  .quick-grid { grid-template-columns: 1fr; }
  .welcome { margin: 8px auto; }
  .welcome-title { font-size: 17px; }
  .chat-foot { padding: 8px 10px 10px; }
  .foot-hint { display: none; }
  .step-sum { max-width: 46vw; }
}
</style>
