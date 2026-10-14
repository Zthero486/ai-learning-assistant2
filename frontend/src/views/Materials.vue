<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>课程资料库</span>
        <div>
          <el-input v-model="courseFilter" placeholder="按课程筛选" style="width:160px;margin-right:8px" clearable @change="load" />
          <el-upload :show-file-list="false" :before-upload="doUpload" accept=".pdf,.docx,.md,.markdown,.txt">
            <el-button type="primary" :loading="uploading">导入资料（PDF/Word/MD/TXT）</el-button>
          </el-upload>
        </div>
      </div>
    </template>
    <el-table :data="materials" v-loading="loading">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="course" label="课程" width="120" />
      <el-table-column prop="filetype" label="类型" width="90" />
      <el-table-column prop="chars" label="字数" width="100" />
      <el-table-column prop="created_at" label="导入时间" width="170" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="view(row)">查看</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="viewerVisible" :title="viewerTitle" size="50%">
    <pre class="content-view">{{ viewerContent }}</pre>
  </el-drawer>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const materials = ref([])
const loading = ref(false)
const uploading = ref(false)
const courseFilter = ref('')
const viewerVisible = ref(false)
const viewerTitle = ref('')
const viewerContent = ref('')

async function load() {
  loading.value = true
  try {
    materials.value = await api.listMaterials(courseFilter.value || undefined)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function doUpload(file) {
  const course = prompt('导入到哪门课程？', courseFilter.value || '未分类')
  if (course === null) return false
  uploading.value = true
  try {
    const r = await api.uploadMaterial(file, course)
    ElMessage.success(`导入成功：${r.title}（${r.chars} 字）`)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    uploading.value = false
  }
  return false
}

async function view(row) {
  viewerTitle.value = row.title
  viewerContent.value = (await api.getMaterial(row.id)).content
  viewerVisible.value = true
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除资料「${row.title}」？`, '删除确认', { type: 'warning' })
  await api.deleteMaterial(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.content-view { white-space: pre-wrap; word-break: break-word; font-family: inherit; line-height: 1.7; }
</style>
