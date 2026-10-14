<template>
  <el-row :gutter="16">
    <!-- 答疑 -->
    <el-col :span="12">
      <el-card class="page-card">
        <template #header>智能答疑（基于你的资料）</template>
        <el-input v-model="ask.material_id" placeholder="可选：资料 ID（在资料页查看）" style="margin-bottom:8px" clearable />
        <el-input
          v-model="ask.question"
          type="textarea"
          :rows="3"
          placeholder="例如：强化学习和监督学习的区别是什么？"
        />
        <el-button type="primary" style="margin-top:10px" :loading="askLoading" @click="doAsk">提问</el-button>
        <el-empty v-if="!askResult" description="回答会基于你导入的课程资料生成" :image-size="70" />
        <pre v-else class="ai-output">{{ askResult }}</pre>
      </el-card>
    </el-col>

    <!-- 总结与薄弱点 -->
    <el-col :span="12">
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
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

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
