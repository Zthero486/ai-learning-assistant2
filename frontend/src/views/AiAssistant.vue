<template>
  <el-card class="page-card">
    <template #header>AI 引擎状态</template>
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <el-tag :type="aiAvailable ? 'success' : 'warning'" size="large">
        {{ statusText }}
      </el-tag>
      <el-button size="small" @click="checkConnection" :loading="checkLoading">检测 AI 连接</el-button>
      <el-button size="small" type="primary" @click="openConfig">配置 API Key</el-button>
      <span class="muted">
        未配置时软件照常可用：答疑走资料检索、总结走抽取式、薄弱点走统计分析。
      </span>
    </div>
    <el-alert
      v-if="checkResult"
      :type="checkResult.ok ? 'success' : 'warning'"
      :closable="false"
      show-icon
      style="margin-top:10px"
      :title="checkResult.message"
      :description="checkResult.ok ? `接口地址：${checkResult.base_url || ''}　模型：${checkResult.model || ''}` : '若提示「网络不通」，多为境内无法直连 Google：在「配置 API Key → 代理地址」填入 http://127.0.0.1:7897（Clash 默认端口）；也可换成国内直连的智谱 GLM-4-Flash。'"
    />
  </el-card>

  <el-dialog v-model="configVisible" title="配置 AI 大模型（可选）" width="560px">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="默认已内置阶跃 StepFun，不填任何东西也能用大模型"
      description="想换成自己的模型：选下方平台预设（阶跃 / 智谱 GLM 都国内直连）→ 粘贴自己的 Key → 保存即可，随时可点「恢复默认」切回内置阶跃。境外平台（如 Google Gemini）才需要填代理地址。"
      style="margin-bottom:14px"
    />
    <el-form label-width="90px">
      <el-form-item label="平台预设">
        <el-select v-model="config.preset" style="width:100%" @change="applyPreset">
          <el-option label="阶跃 StepFun（内置默认，国内直连）" value="stepfun" />
          <el-option label="智谱 GLM（国内直连，永久免费）" value="zhipu" />
          <el-option label="MiniMax M Plan（订阅 Key）" value="minimax" />
          <el-option label="硅基流动 SiliconFlow（9B 以下免费）" value="siliconflow" />
          <el-option label="阿里云百炼（新用户额度）" value="dashscope" />
          <el-option label="DeepSeek（付费，推理强）" value="deepseek" />
          <el-option label="OpenRouter（免费模型）" value="openrouter" />
          <el-option label="Google Gemini（境外，需代理）" value="gemini" />
        </el-select>
      </el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="config.api_key" placeholder="粘贴自己的 Key；留空保存＝恢复内置阶跃默认" show-password />
      </el-form-item>
      <el-form-item label="接口地址">
        <el-input v-model="config.base_url" />
      </el-form-item>
      <el-form-item label="模型名">
        <el-input v-model="config.model" />
      </el-form-item>
      <el-form-item label="代理地址">
        <el-input v-model="config.proxy" placeholder="可留空；境内访问 Google 填 http://127.0.0.1:7897" />
      </el-form-item>
      <el-form-item label="配置文件">
        <span class="muted">{{ config.env_path || '程序目录下的 .env' }}</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="configVisible = false">取消</el-button>
      <el-button @click="resetToBuiltin" :loading="saveLoading">恢复默认（阶跃）</el-button>
      <el-button type="primary" :loading="saveLoading" @click="saveConfig">保存并生效</el-button>
    </template>
  </el-dialog>

  <el-row :gutter="16">
    <!-- 答疑 -->
    <el-col :xs="24" :sm="24" :md="12">
      <el-card class="page-card">
        <template #header>智能答疑（基于你的资料）</template>
        <el-input v-model="ask.material_id" placeholder="可选：资料 ID（在资料页查看）" style="margin-bottom:8px" clearable />
        <el-input
          v-model="ask.question"
          type="textarea"
          :rows="3"
          placeholder="例如：商鞅变法为什么能在秦国推行？郡县制与分封制的根本区别是什么？"
        />
        <el-button type="primary" style="margin-top:10px" :loading="askLoading" @click="doAsk">提问</el-button>
        <el-empty v-if="!askResult" description="回答会基于你导入的史料生成" :image-size="70" />
        <pre v-else class="ai-output">{{ askResult }}</pre>
      </el-card>
    </el-col>

    <!-- 总结与薄弱点 -->
    <el-col :xs="24" :sm="24" :md="12">
      <el-card class="page-card">
        <template #header>资料总结</template>
        <div style="display:flex;gap:8px;margin-bottom:8px">
          <el-input v-model="summarize.material_id" placeholder="输入资料 ID" style="width:200px" />
          <el-button type="primary" :loading="sumLoading" @click="doSummarize">生成总结</el-button>
        </div>
        <el-empty v-if="!sumResult" description="AI 将基于资料内容做结构化总结" :image-size="70" />
        <pre v-else class="ai-output">{{ sumResult }}</pre>
      </el-card>

      <el-card class="page-card">
        <template #header>薄弱知识点分析</template>
        <el-button type="primary" :loading="weakLoading" @click="doWeak">分析我的薄弱点</el-button>
        <div v-if="weakKps.length" style="margin-top:10px">
          <el-tag v-for="k in weakKps" :key="k.kp_id" type="danger" style="margin:0 6px 6px 0">
            {{ k.title }}（正确率 {{ k.accuracy }}%）
          </el-tag>
        </div>
        <pre v-if="weakResult" class="ai-output">{{ weakResult }}</pre>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const aiAvailable = ref(null)
const aiSource = ref('none')
const checkLoading = ref(false)
const checkResult = ref(null)
const configVisible = ref(false)
const saveLoading = ref(false)
const presets = ref({})
const config = ref({ preset: 'stepfun', api_key: '', base_url: '', model: '', proxy: '', env_path: '' })

const statusText = computed(() => {
  if (aiAvailable.value === null) return '检测中…'
  if (!aiAvailable.value) return '未配置 API Key（规则引擎模式）'
  return aiSource.value === 'builtin' ? '内置阶跃 StepFun（默认）' : '已接入自建大模型'
})

async function loadStatus() {
  try {
    const h = await api.aiHealth()
    aiAvailable.value = h.ai_available
    aiSource.value = h.ai_source || 'none'
  } catch {
    aiAvailable.value = null
  }
}

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

async function saveConfig() {
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
    await checkConnection()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}

async function resetToBuiltin() {
  saveLoading.value = true
  try {
    const r = await api.saveAiConfig({ api_key: '', base_url: '', model: '', proxy: '' })
    ElMessage.success(r.message)
    configVisible.value = false
    await loadStatus()
    await checkConnection()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}

async function checkConnection() {
  checkLoading.value = true
  try {
    const r = await api.aiTest()
    checkResult.value = r
    aiAvailable.value = r.ok
    if (r.ok) ElMessage.success('AI 连接正常')
  } catch (e) {
    checkResult.value = { ok: false, message: e.message }
    ElMessage.error(e.message)
  } finally {
    checkLoading.value = false
  }
}

onMounted(loadStatus)

const ask = ref({ question: '', material_id: '' })
const askLoading = ref(false)
const askResult = ref('')
const summarize = ref({ material_id: '' })
const sumLoading = ref(false)
const sumResult = ref('')
const weakLoading = ref(false)
const weakResult = ref('')
const weakKps = ref([])

function modeTag(mode) {
  return mode === 'ai' ? '【大模型】' : '【规则引擎降级 · 未配置 API key】'
}

async function doAsk() {
  if (!ask.value.question.trim()) return ElMessage.warning('先输入问题')
  askLoading.value = true
  try {
    const r = await api.aiAsk({ question: ask.value.question, material_id: ask.value.material_id || null })
    askResult.value = modeTag(r.mode) + '\n\n' + r.answer
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    askLoading.value = false
  }
}

async function doSummarize() {
  if (!summarize.value.material_id) return ElMessage.warning('先输入资料 ID')
  sumLoading.value = true
  try {
    const r = await api.aiSummarize({ material_id: Number(summarize.value.material_id) })
    sumResult.value = modeTag(r.mode) + '\n\n' + r.summary
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    sumLoading.value = false
  }
}

async function doWeak() {
  weakLoading.value = true
  try {
    const r = await api.aiWeakAnalysis({})
    weakKps.value = r.weak_kps || []
    weakResult.value = modeTag(r.mode) + '\n\n' + r.advice
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    weakLoading.value = false
  }
}
</script>

<style scoped>
.ai-output {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.7;
  background: #f8f9fb;
  border-radius: 8px;
  padding: 12px;
  margin-top: 10px;
}
</style>
