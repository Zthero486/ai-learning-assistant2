<template>
  <el-dialog v-model="visible" width="560px" :show-close="false" class="gs-dialog" @opened="focusInput">
    <div class="gs-box">
      <div class="gs-input-row">
        <el-icon class="gs-icon"><Search /></el-icon>
        <input
          ref="inputRef"
          v-model="query"
          class="gs-input"
          placeholder="搜索资料 / 知识点 / 题目 / 任务…"
          @input="onInput"
          @keydown.esc="close"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter="go(flat[active]?.route)"
        />
        <span class="gs-kbd">ESC</span>
      </div>

      <div v-if="loading" class="gs-empty">搜索中…</div>
      <div v-else-if="query && !flat.length" class="gs-empty">没有找到「{{ query }}」相关内容</div>
      <div v-else-if="!query" class="gs-empty">输入关键词，回车或点击结果跳转</div>

      <div v-else class="gs-results">
        <div v-for="g in groups" :key="g.key">
          <div v-if="g.items.length" class="gs-group">{{ g.label }}</div>
          <div
            v-for="item in g.items"
            :key="g.key + item.id"
            class="gs-item"
            :class="{ active: item.route === flat[active]?.route }"
            @click="go(item.route)"
            @mousemove="active = flat.findIndex(f => f.route === item.route)"
          >
            <div class="gs-title">{{ item.title }}</div>
            <div v-if="item.snippet" class="gs-snippet">{{ item.snippet }}</div>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
// Ctrl+K 全局搜索：前端防抖 250ms，结果四类分组，点击/回车跳转对应页面
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const visible = ref(false)
const query = ref('')
const loading = ref(false)
const inputRef = ref(null)
const active = ref(0)
let result = { materials: [], knowledge_points: [], questions: [], tasks: [] }
let timer = null

const groups = computed(() => [
  { key: 'materials', label: '📄 课程资料', items: result.materials.map(m => ({ ...m, title: `${m.title}（${m.course}）`, route: '/materials' })) },
  { key: 'kps', label: '💡 知识点', items: result.knowledge_points.map(k => ({ ...k, title: `${k.title}（${k.course}）`, route: '/knowledge' })) },
  { key: 'questions', label: '❓ 题目', items: result.questions.map(q => ({ ...q, title: q.kp_title || '题目', route: '/practice' })) },
  { key: 'tasks', label: '✅ 学习任务', items: result.tasks.map(t => ({ ...t, title: t.title, route: '/tasks' })) },
])
const flat = computed(() => groups.value.flatMap(g => g.items))

function open() {
  visible.value = true
  query.value = ''
  result = { materials: [], knowledge_points: [], questions: [], tasks: [] }
  active.value = 0
}
function close() { visible.value = false }
function focusInput() { inputRef.value?.focus() }

function onInput() {
  clearTimeout(timer)
  const q = query.value.trim()
  if (!q) { result = { materials: [], knowledge_points: [], questions: [], tasks: [] }; return }
  timer = setTimeout(async () => {
    loading.value = true
    try {
      result = await api.search(q)
      active.value = 0
    } catch { /* 401 由 api 层统一处理 */ }
    finally { loading.value = false }
  }, 250)
}

function move(d) {
  if (!flat.value.length) return
  active.value = (active.value + d + flat.value.length) % flat.value.length
}
function go(route) {
  if (!route) return
  close()
  if (router.currentRoute.value.path !== route) router.push(route)
}

function onKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    visible.value ? close() : open()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

defineExpose({ open })
</script>

<style>
.gs-dialog .el-dialog__header { display: none; }
.gs-dialog .el-dialog__body { padding: 0; }
</style>
<style scoped>
.gs-box { padding: 12px; }
.gs-input-row { display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #e4e7ed; padding-bottom: 10px; }
.gs-icon { color: #909399; font-size: 18px; }
.gs-input { flex: 1; border: none; outline: none; font-size: 15px; background: transparent; }
.gs-kbd { font-size: 11px; color: #c0c4cc; border: 1px solid #e4e7ed; border-radius: 4px; padding: 1px 5px; }
.gs-results { max-height: 420px; overflow: auto; margin-top: 6px; }
.gs-group { font-size: 12px; color: #909399; padding: 10px 8px 4px; }
.gs-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; }
.gs-item.active, .gs-item:hover { background: #f0f6ff; }
.gs-title { font-size: 14px; color: #303133; }
.gs-snippet { font-size: 12px; color: #909399; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-empty { text-align: center; color: #909399; font-size: 13px; padding: 32px 0; }
</style>
