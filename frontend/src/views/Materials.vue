<template>
  <el-card class="page-card">
    <template #header>
      <div class="mats-head">
        <span class="mats-title">史料与笔记</span>
        <div class="mats-tools">
          <el-select v-model="uploadCourse" placeholder="导入到" style="width:130px">
            <el-option v-for="c in COURSES" :key="c.v" :label="c.l" :value="c.v" />
            <el-option label="未分类" value="未分类" />
          </el-select>
          <el-input v-model="courseFilter" placeholder="按时期筛选" style="width:150px" clearable @change="load" />
          <el-upload
            :show-file-list="false"
            :before-upload="doUpload"
            accept=".pdf,application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.md,.markdown,.txt,text/plain,text/markdown"
          >
            <el-button type="primary" :loading="uploading" title="支持 PDF / Word(.docx) / Markdown / TXT，最大 20MB">
              导入史料/笔记
            </el-button>
          </el-upload>
        </div>
      </div>
    </template>
    <el-table :data="materials" v-loading="loading">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="course" label="时期" width="120" />
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

  <AiInline context="史料笔记" />
</template>

<script setup>
import AiInline from '../components/AiInline.vue'
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { auth } from '../api'

const materials = ref([])
const loading = ref(false)
const uploading = ref(false)
const courseFilter = ref('')
const uploadCourse = ref(auth.track() || '未分类')
const viewerVisible = ref(false)
const viewerTitle = ref('')
const viewerContent = ref('')

const COURSES = [
  { v: 'party', l: '党史' },
  { v: 'prc', l: '新中国史' },
  { v: 'reform', l: '改革开放史' },
  { v: 'socialism', l: '社会主义发展史' },
]

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

// 关键：移动端（iOS Safari / 部分平板 WebView）在打开过文件选择器后，
// 若中间还 await 任何交互（如弹窗问课程），File 对象会失效、上传成 0 字节。
// 所以这里先同步做 Blob 快照，之后只操作快照；课程改为页面上下拉选择。
async function doUpload(file) {
  const name = file.name || 'upload'
  let blob
  try {
    blob = file.slice(0, file.size, file.type || '')
  } catch {
    blob = file
  }
  if (!blob || !blob.size) {
    ElMessage({ type: 'error', message: '读取到的文件为空，请重新选择文件', duration: 8000, showClose: true })
    return false
  }
  if (blob.size > 20 * 1024 * 1024) {
    ElMessage({ type: 'error', message: `文件 ${(blob.size / 1048576).toFixed(1)}MB 超过 20MB 限制`, duration: 8000, showClose: true })
    return false
  }
  const course = uploadCourse.value || '未分类'
  uploading.value = true
  ElMessage({ type: 'info', message: `正在上传 ${name}（${(blob.size / 1048576).toFixed(1)}MB），大文件请稍候…`, duration: 4000 })
  try {
    const r = await api.uploadMaterial(blob, course, name)
    ElMessage.success(`导入成功：${r.title}（${r.chars} 字）`)
    await load()
  } catch (e) {
    ElMessage({ type: 'error', message: '导入失败：' + e.message, duration: 9000, showClose: true })
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
.mats-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
.mats-title { white-space: nowrap; font-weight: 600; }
.mats-tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
</style>
