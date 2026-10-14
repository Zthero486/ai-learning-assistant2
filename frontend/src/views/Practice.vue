<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>练习</span>
        <el-select v-model="kpFilter" placeholder="按知识点筛选" clearable style="width:200px" @change="load">
          <el-option v-for="k in kps" :key="k.id" :label="k.title" :value="k.id" />
        </el-select>
      </div>
    </template>
    <el-empty v-if="!questions.length" description="还没有题目：去「知识点」页对某个知识点点「AI 出题」" />
    <div v-for="(q, idx) in questions" :key="q.id" class="q-card">
      <div class="q-head">
        <el-tag size="small">{{ q.source === 'ai' ? 'AI 题' : '规则题' }}</el-tag>
        <el-tag size="small" type="info" style="margin-left:6px">{{ q.kp_title || '未关联' }}</el-tag>
        <span class="q-text">{{ idx + 1 }}. {{ q.question }}</span>
      </div>
      <div class="q-body">
        <el-input v-model="answers[q.id]" placeholder="输入你的答案" style="max-width:480px" />
        <el-button type="primary" style="margin-left:10px" @click="submit(q)">提交</el-button>
        <el-button text @click="toggleAnswer(q)">看答案</el-button>
        <div v-if="revealed[q.id]" class="answer">参考答案：{{ q.answer }}</div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const questions = ref([])
const kps = ref([])
const kpFilter = ref(null)
const answers = ref({})
const revealed = ref({})

async function load() {
  try {
    questions.value = await api.listQuestions(kpFilter.value)
    kps.value = await api.listKps()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function toggleAnswer(q) {
  revealed.value[q.id] = !revealed.value[q.id]
}

async function submit(q) {
  const ans = (answers.value[q.id] || '').trim()
  if (!ans) {
    ElMessage.warning('先写下你的答案再提交')
    return
  }
  // v1：提交后展示参考答案，由自己判对错（v2 可引入 AI 智能判分）
  const correct = await new Promise((resolve) => {
    ElMessageBox.confirm(
      `你的答案：${ans}\n参考答案：${q.answer}`,
      '自我判分',
      { confirmButtonText: '答对了', cancelButtonText: '答错了', type: 'question' },
    ).then(() => resolve(true)).catch(() => resolve(false))
  })
  await api.submitPractice({ question_id: q.id, answer: ans, correct })
  ElMessage.success(correct ? '记为正确 ✓' : '已记入错题本 ✗')
  answers.value[q.id] = ''
  revealed.value[q.id] = false
}

onMounted(load)
</script>

<style scoped>
.q-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.q-head { margin-bottom: 10px; }
.q-text { margin-left: 10px; font-weight: 600; }
.answer { margin-top: 10px; color: #67c23a; }
</style>
