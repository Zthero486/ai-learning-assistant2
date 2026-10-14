<template>
  <el-card class="page-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>知识点管理</span>
        <el-button type="primary" @click="dialogVisible = true">新建知识点</el-button>
      </div>
    </template>
    <el-table :data="kps" v-loading="loading">
      <el-table-column prop="title" label="知识点" min-width="140" />
      <el-table-column prop="course" label="课程" width="110" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="material_title" label="来源资料" width="150">
        <template #default="{ row }">{{ row.material_title || '—' }}</template>
      </el-table-column>
      <el-table-column prop="question_count" label="关联题目" width="90" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="edit(row)">编辑</el-button>
          <el-button size="small" type="primary" @click="genQuestions(row)">AI 出题</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑知识点' : '新建知识点'" width="520px">
    <el-form label-width="80px">
      <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
      <el-form-item label="课程"><el-input v-model="form.course" placeholder="如：人工智能" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="来源资料">
        <el-select v-model="form.material_id" clearable placeholder="可选：关联一份资料" style="width:100%">
          <el-option v-for="m in materials" :key="m.id" :label="m.title" :value="m.id" />
        </el-select>
      </el-form-item>
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

const kps = ref([])
const materials = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = ref({ id: null, title: '', course: '未分类', description: '', material_id: null })

async function load() {
  loading.value = true
  try {
    kps.value = await api.listKps()
    materials.value = await api.listMaterials()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function edit(row) {
  form.value = { ...row }
  dialogVisible.value = true
}

async function save() {
  try {
    if (form.value.id) {
      await api.updateKp(form.value.id, form.value)
    } else {
      await api.createKp(form.value)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    form.value = { id: null, title: '', course: '未分类', description: '', material_id: null }
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function genQuestions(row) {
  try {
    const r = await api.generateQuestions({ kp_id: row.id, num: 5 })
    if (r.source === 'ai') {
      ElMessage.success(`大模型生成了 ${r.generated} 道题`)
    } else {
      ElMessage.warning(`规则引擎生成了 ${r.generated} 道题（未配置 AI key）`)
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除知识点「${row.title}」？其关联题目也会删除。`, '删除确认', { type: 'warning' })
  await api.deleteKp(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>
