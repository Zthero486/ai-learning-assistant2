<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>错题本</span>
        <el-checkbox v-model="onlyUnresolved" label="只看未解决" @change="load" />
      </div>
    </template>
    <el-empty v-if="!items.length" description="错题本是空的，继续保持！" />
    <div v-for="w in items" :key="w.id" class="w-card">
      <div class="w-head">
        <el-tag type="danger" size="small">错 {{ w.wrong_count }} 次</el-tag>
        <el-tag type="info" size="small" style="margin-left:6px">{{ w.kp_title || '未关联' }}</el-tag>
        <el-tag v-if="w.review_marked" type="warning" size="small" style="margin-left:6px">待重点复习</el-tag>
        <span class="w-date muted">{{ w.last_wrong_at }}</span>
      </div>
      <div class="w-question">{{ w.question }}</div>
      <div class="w-answer">参考答案：{{ w.answer }}</div>
      <div class="w-actions">
        <el-button size="small" @click="markReview(w)">{{ w.review_marked ? '取消重点标记' : '标记重点复习' }}</el-button>
        <el-button size="small" type="success" @click="resolve(w)">标记已掌握</el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const items = ref([])
const onlyUnresolved = ref(true)

async function load() {
  try {
    items.value = await api.wrongBook(onlyUnresolved.value)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function markReview(w) {
  await api.updateWrong(w.id, { review_marked: w.review_marked ? 0 : 1 })
  await load()
}

async function resolve(w) {
  await api.updateWrong(w.id, { resolved: 1 })
  ElMessage.success('很好，又攻克一道错题！')
  await load()
}

onMounted(load)
</script>

<style scoped>
.w-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.w-head { display: flex; align-items: center; margin-bottom: 8px; }
.w-date { margin-left: auto; }
.w-question { font-weight: 600; margin-bottom: 6px; }
.w-answer { color: #67c23a; margin-bottom: 10px; }
.w-actions { display: flex; gap: 8px; }
</style>
