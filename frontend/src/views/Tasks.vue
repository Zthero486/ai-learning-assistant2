<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>学习任务</span>
        <el-button type="primary" @click="dialogVisible = true">新建任务</el-button>
      </div>
    </template>
    <el-table :data="tasks" v-loading="loading">
      <el-table-column prop="title" label="任务" min-width="160" />
      <el-table-column prop="course" label="课程" width="110" />
      <el-table-column prop="kp_title" label="关联知识点" width="130">
        <template #default="{ row }">{{ row.kp_title || '—' }}</template>
      </el-table-column>
      <el-table-column prop="due_date" label="截止日期" width="120">
        <template #default="{ row }">
          <span :class="{ 'overdue': row.overdue }">{{ row.due_date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="140">
        <template #default="{ row }">
          <el-select :model-value="row.status" size="small" @change="(s) => setStatus(row, s)">
            <el-option label="待办" value="todo" />
            <el-option label="进行中" value="doing" />
            <el-option label="已完成" value="done" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" title="新建学习任务" width="520px">
    <el-form label-width="90px">
      <el-form-item label="任务标题"><el-input v-model="form.title" /></el-form-item>
      <el-form-item label="课程"><el-input v-model="form.course" /></el-form-item>
      <el-form-item label="关联知识点">
        <el-select v-model="form.kp_id" clearable style="width:100%">
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
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const tasks = ref([])
const kps = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = ref({ title: '', course: '未分类', kp_id: null, due_date: null, description: '' })

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

async function save() {
  try {
    await api.createTask(form.value)
    ElMessage.success('任务已创建')
    dialogVisible.value = false
    form.value = { title: '', course: '未分类', kp_id: null, due_date: null, description: '' }
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function setStatus(row, status) {
  try {
    await api.setTaskStatus(row.id, status)
    row.status = status
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除任务「${row.title}」？`, '删除确认', { type: 'warning' })
  await api.deleteTask(row.id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.overdue { color: #f56c6c; font-weight: 600; }
</style>
