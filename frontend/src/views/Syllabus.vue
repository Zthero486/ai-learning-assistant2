<template>
  <div v-loading="loading">
    <div class="page-head">
      <div>
        <h2 class="title">{{ data.track_name }} · 教材目录</h2>
        <div class="muted">
          {{ data.chapter_count }} 章 {{ data.section_count }} 节 · 已建知识点 {{ data.total_kp }} 个 ·
          题目 {{ data.total_q }} 道
        </div>
      </div>
      <el-button size="small" plain @click="$router.push('/welcome')">切换课程</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :sm="24" :md="9">
        <el-card class="page-card" shadow="never" body-style="padding: 8px 0;">
          <div v-for="ch in data.chapters" :key="ch.code" class="chapter">
            <div class="chapter-head" @click="toggle(ch.code)">
              <el-icon class="caret" :class="{ open: opened.includes(ch.code) }"><ArrowRight /></el-icon>
              <span class="chapter-title">{{ ch.title }}</span>
              <span class="chapter-period">{{ ch.period }}</span>
              <span class="chapter-stat" v-if="ch.kp">{{ ch.kp }}</span>
            </div>
            <div v-show="opened.includes(ch.code)" class="sections">
              <div
                v-for="s in ch.sections"
                :key="s.code"
                class="section"
                :class="{ active: s.code === active }"
                @click="pick(s.code)"
              >
                <span class="sec-title">{{ s.title }}</span>
                <span class="sec-stat" v-if="s.kp">{{ s.kp }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="24" :md="15">
        <el-card class="page-card" shadow="never" v-if="node">
          <div class="node-path">{{ node.path }}</div>
          <div class="node-meta">
            <el-tag size="small" effect="plain">{{ node.period || '—' }}</el-tag>
            <span class="muted">知识点 {{ node.kps.length }} 个 · 题目 {{ node.question_count }} 道 · 相关事件 {{ node.events.length }} 条</span>
          </div>

          <div class="block-head">
            <span>本节知识点</span>
            <div>
              <el-button size="small" @click="openKp">新增知识点</el-button>
              <el-button size="small" type="primary" plain @click="$router.push('/practice')">去自测</el-button>
            </div>
          </div>

          <el-empty v-if="!node.kps.length" description="这一节还没有知识点，先加一条" :image-size="70" />
          <div v-for="k in node.kps" :key="k.id" class="kp-item">
            <div class="kp-title">
              {{ k.title }}
              <el-tag v-if="k.exam_type" size="small" type="info" effect="plain">{{ examLabel(k.exam_type) }}</el-tag>
            </div>
            <div class="kp-desc muted">{{ k.description || '（无描述）' }}</div>
          </div>

          <template v-if="node.events.length">
            <div class="block-head"><span>相关事件 / 会议</span></div>
            <div v-for="e in node.events" :key="e.id" class="event-item">
              <span class="event-year">{{ e.year_text }}</span>
              <span class="event-title">{{ e.title }}</span>
              <el-tag size="small" effect="plain">{{ kindLabel(e.kind) }}</el-tag>
              <div class="event-digest muted">{{ e.impact || e.place }}</div>
            </div>
          </template>
        </el-card>
        <el-card v-else class="page-card" shadow="never">
          <el-empty description="左侧选一节开始" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="kpDlg" title="新增知识点" width="460px">
      <el-form label-width="72px">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="如：遵义会议的历史地位" />
        </el-form-item>
        <el-form-item label="要点">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="一两句话说清它是什么、为什么重要" />
        </el-form-item>
        <el-form-item label="考法">
          <el-select v-model="form.exam_type" placeholder="按思政课考法归类" style="width: 100%">
            <el-option label="史实识记（时间/会议/文件）" value="recall" />
            <el-option label="时序定位（排序/年代判断）" value="sequence" />
            <el-option label="史论结合（简答/论述）" value="argument" />
            <el-option label="现实联系（材料分析）" value="apply" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kpDlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveKp">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import api, { auth } from '../api'

const route = useRoute()
const loading = ref(true)
const data = ref({ chapters: [], chapter_count: 0, section_count: 0, total_kp: 0, total_q: 0, track_name: '' })
const opened = ref([])
const active = ref('')
const node = ref(null)
const kpDlg = ref(false)
const saving = ref(false)
const form = reactive({ title: '', description: '', exam_type: 'recall' })

const EXAM = { recall: '史实识记', sequence: '时序定位', argument: '史论结合', apply: '现实联系' }
const KIND = { meeting: '会议', event: '事件', document: '文件' }
const examLabel = (k) => EXAM[k] || k
const kindLabel = (k) => KIND[k] || '事件'

function toggle(code) {
  const i = opened.value.indexOf(code)
  if (i >= 0) opened.value.splice(i, 1)
  else opened.value.push(code)
}

async function pick(code) {
  active.value = code
  try {
    node.value = await api.syllabusNode(code)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openKp() {
  form.title = ''
  form.description = ''
  form.exam_type = 'recall'
  kpDlg.value = true
}

async function saveKp() {
  if (!form.title.trim()) {
    ElMessage.warning('标题不能为空')
    return
  }
  saving.value = true
  try {
    await api.createKp({
      title: form.title,
      description: form.description,
      exam_type: form.exam_type,
      node_code: active.value,
      course: data.value.track_name,
    })
    kpDlg.value = false
    ElMessage.success('已加入本节')
    await refreshNode()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function refreshNode() {
  node.value = await api.syllabusNode(active.value)
  data.value = await api.syllabus(auth.track())
}

onMounted(async () => {
  try {
    const track = auth.track() || route.query.track || ''
    data.value = await api.syllabus(track)
    if (data.value.chapters.length) {
      opened.value = [data.value.chapters[0].code]
      const first = data.value.chapters[0].sections[0]
      if (first) await pick(first.code)
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.title { font-size: 18px; margin: 0 0 4px; color: #303133; }
.muted { color: #909399; font-size: 13px; }
.chapter { border-bottom: 1px solid #f0f2f5; }
.chapter:last-child { border-bottom: none; }
.chapter-head { display: flex; align-items: center; gap: 6px; padding: 10px 14px; cursor: pointer; }
.chapter-head:hover { background: #fafafa; }
.caret { font-size: 12px; color: #c0c4cc; transition: transform .15s; }
.caret.open { transform: rotate(90deg); }
.chapter-title { flex: 1; font-size: 13px; color: #303133; line-height: 1.5; }
.chapter-period { font-size: 11px; color: #c0c4cc; }
.chapter-stat { font-size: 11px; color: #409eff; background: #ecf5ff; border-radius: 8px; padding: 0 6px; }
.sections { padding-bottom: 6px; }
.section { display: flex; align-items: center; gap: 8px; padding: 7px 14px 7px 30px; cursor: pointer; font-size: 12px; color: #606266; line-height: 1.5; }
.section:hover { background: #f5f7fa; }
.section.active { background: #ecf5ff; color: #409eff; }
.sec-title { flex: 1; }
.sec-stat { color: #409eff; }
.node-path { font-size: 15px; font-weight: 600; color: #303133; line-height: 1.6; }
.node-meta { display: flex; align-items: center; gap: 10px; margin: 8px 0 18px; }
.block-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #606266; margin: 16px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #f0f2f5; }
.kp-item { padding: 8px 0; border-bottom: 1px dashed #f0f2f5; }
.kp-title { font-size: 13px; color: #303133; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.kp-desc { font-size: 12px; margin-top: 4px; line-height: 1.6; }
.event-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 6px 0; font-size: 13px; color: #303133; }
.event-year { color: #409eff; font-variant-numeric: tabular-nums; min-width: 52px; }
.event-digest { flex-basis: 100%; font-size: 12px; padding-left: 60px; }
</style>
