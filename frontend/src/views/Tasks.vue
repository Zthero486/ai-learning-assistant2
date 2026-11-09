<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
        <span>复习任务</span>
        <div style="display:flex;gap:8px">
          <el-button v-if="dupCount" size="small" type="warning" plain @click="dedupe">
            合并 {{ dupCount }} 条重复
          </el-button>
          <el-button v-if="doneCount" size="small" @click="clearDone">清掉已完成</el-button>
          <el-button type="primary" @click="dialogVisible = true">新建任务</el-button>
        </div>
      </div>
    </template>

    <el-empty v-if="!loading && !tasks.length" description="还没有任务，点右上角新建，或让 AI 帮你排计划" />

    <div v-for="t in sorted" :key="t.id" class="task" :class="{ done: t.status === 'done' }">
      <div class="tick" :title="t.status === 'done' ? '标记为未完成' : '标记完成'" @click="toggle(t)">
        <el-icon v-if="t.status === 'done'"><Check /></el-icon>
      </div>

      <div class="body">
        <div class="t-title">
          <span class="name">{{ t.title }}</span>
          <el-tag v-if="t.overdue && t.status !== 'done'" size="small" type="danger" effect="plain">已过期</el-tag>
          <el-tag v-else-if="isToday(t.due_date) && t.status !== 'done'" size="small" type="warning" effect="plain">今天</el-tag>
          <el-tag v-else-if="t.status === 'done'" size="small" type="info" effect="plain">已完成</el-tag>
        </div>
        <div v-if="t.description" class="t-desc">{{ t.description }}</div>
        <div class="t-meta">
          <span class="muted">{{ t.due_date || '无截止' }}</span>
          <template v-if="t.kp_title">
            <span class="dot">·</span>
            <a class="kp-link" @click="goReview(t)">{{ t.kp_title }} → 去复习</a>
          </template>
        </div>
      </div>

      <el-button class="del" size="small" text type="danger" @click="remove(t)">删除</el-button>
    </div>
  </el-card>

  <el-dialog v-model="dialogVisible" title="新建复习任务" width="520px">
    <el-form label-width="90px">
      <el-form-item label="任务标题"><el-input v-model="form.title" /></el-form-item>
      <el-form-item label="关联知识点">
        <el-select v-model="form.kp_id" clearable filterable style="width:100%">
          <el-option v-for="k in kps" :key="k.id" :label="k.title" :value="k.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="截止日期">
        <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <AiInline context="复习任务" />
</template>

<script setup>
import AiInline from '../components/AiInline.vue'
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const tasks = ref([])
const kps = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = ref({ title: '', kp_id: null, due_date: null, description: '' })

const doneCount = computed(() => tasks.value.filter((t) => t.status === 'done').length)
// 重复 = 同标题且同截止日期（AI 排计划与手动新建最容易撞）
const dupCount = computed(() => {
  const seen = new Map()
  for (const t of tasks.value) {
    if (t.status === 'done') continue
    const key = `${t.title}|${t.due_date || ''}`
    seen.set(key, (seen.get(key) || 0) + 1)
  }
  return [...seen.values()].reduce((n, c) => n + c - 1, 0)
})

// 排序：已完成沉底；未完成按 已过期 > 今天 > 有日期升序 > 无日期
const sorted = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  const rank = (t) => {
    if (t.status === 'done') return 3
    if (!t.due_date) return 2
    if (t.due_date < today) return 0
    if (t.due_date === today) return 1
    return 2
  }
  return [...tasks.value].sort((a, b) => {
    const r = rank(a) - rank(b)
    if (r) return r
    const da = a.due_date || '9999-99-99'
    const db = b.due_date || '9999-99-99'
    return da < db ? -1 : da > db ? 1 : a.id - b.id
  })
})

const isToday = (d) => d && d === new Date().toISOString().slice(0, 10)

async function load() {
  loading.value = true
  try {
    tasks.value = await api.listTasks()
    kps.value = await api.listKps()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function toggle(t) {
  const next = t.status === 'done' ? 'todo' : 'done'
  t.status = next // 乐观更新，失败再回滚
  try {
    await api.setTaskStatus(t.id, next)
  } catch (e) {
    t.status = next === 'done' ? 'todo' : 'done'
    ElMessage.error(e.message)
  }
}

async function save() {
  try {
    await api.createTask(form.value)
    ElMessage.success('任务已创建')
    dialogVisible.value = false
    form.value = { title: '', kp_id: null, due_date: null, description: '' }
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(t) {
  await ElMessageBox.confirm(`确认删除任务「${t.title}」？`, '删除确认', { type: 'warning' })
  await api.deleteTask(t.id)
  await load()
}

async function clearDone() {
  const done = tasks.value.filter((t) => t.status === 'done')
  await ElMessageBox.confirm(`清掉 ${done.length} 条已完成任务？`, '确认', { type: 'warning' })
  for (const t of done) await api.deleteTask(t.id)
  ElMessage.success('已清理')
  await load()
}

async function dedupe() {
  const seen = new Map()
  const dups = []
  for (const t of tasks.value) {
    if (t.status === 'done') continue
    const key = `${t.title}|${t.due_date || ''}`
    if (seen.has(key)) dups.push(t)
    else seen.set(key, t)
  }
  if (!dups.length) return
  await ElMessageBox.confirm(
    `发现 ${dups.length} 条重复任务：${dups.map((d) => `「${d.title}」`).join('、')}，删除重复的这些？`,
    '合并重复', { type: 'warning' },
  )
  for (const d of dups) await api.deleteTask(d.id)
  ElMessage.success('已合并')
  await load()
}

function goReview(t) {
  if (t.kp_node) router.push({ path: '/syllabus', query: { node: t.kp_node } })
  else router.push('/syllabus')
}

onMounted(load)
</script>

<style scoped>
.task { display: flex; align-items: flex-start; gap: 12px; padding: 12px 4px; border-bottom: 1px solid #f0f2f5; }
.task:last-child { border-bottom: none; }
.tick { flex: none; width: 20px; height: 20px; margin-top: 2px; border: 2px solid #c0c4cc; border-radius: 50%;
        display: flex; align-items: center; justify-content: center; cursor: pointer; color: #fff; transition: all .15s; }
.tick:hover { border-color: #67c23a; }
.task.done .tick { background: #67c23a; border-color: #67c23a; }
.body { flex: 1; min-width: 0; }
.t-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.name { font-size: 14px; color: #303133; line-height: 1.5; }
.task.done .name { text-decoration: line-through; color: #c0c4cc; }
.t-desc { font-size: 12px; color: #909399; margin-top: 2px; line-height: 1.5; }
.t-meta { font-size: 12px; margin-top: 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.muted { color: #909399; }
.t-meta .overdue { color: #f56c6c; font-weight: 600; }
.dot { color: #dcdfe6; }
.kp-link { color: #409eff; cursor: pointer; }
.kp-link:hover { text-decoration: underline; }
.del { flex: none; }
@media (max-width: 768px) {
  .task { padding: 10px 0; }
}
</style>
