<template>
  <el-card class="page-card">
    <template #header>
      <div class="wb-head">
        <div class="wb-head-left">
          <span>错题本</span>
          <el-radio-group v-model="view" size="small" @change="load">
            <el-radio-button value="all">全部错题</el-radio-button>
            <el-radio-button value="due">今日复习{{ dueCount ? `（${dueCount}）` : '' }}</el-radio-button>
          </el-radio-group>
          <el-checkbox v-if="view === 'all'" v-model="onlyUnresolved" @change="load">
            只看未解决
          </el-checkbox>
        </div>
        <div class="wb-head-right">
          <el-button size="small" type="primary" plain @click="aiDiagnose">AI 错因诊断</el-button>
          <el-button size="small" type="warning" plain :loading="gening" @click="genSimilar">
            AI 出同类题
          </el-button>
          <el-button size="small" @click="doExportCsv" :loading="exporting">导出 CSV</el-button>
          <el-button size="small" @click="doPrint">导出 PDF</el-button>
        </div>
      </div>
    </template>

    <!-- 今日复习：到期的排在最前；一条都没到期时给出「下次什么时候来」 -->
    <el-alert
      v-if="view === 'due' && !items.length"
      type="success"
      show-icon
      :closable="false"
      title="今天没有到期要复习的错题"
      :description="dueHint"
    />

    <el-empty v-if="view === 'all' && !items.length" description="错题本是空的，继续保持！" />

    <!-- 按课程分组：默认只展开第一组、组内先露 3 条，保证不滚动就能看到底部 AI 对话框 -->
    <div v-for="g in groups" :key="g.key" class="w-group">
      <div class="w-group-head" @click="st(g).open = !st(g).open">
        <el-tag :type="g.tag" size="small" effect="dark">{{ g.name }}</el-tag>
        <span class="muted w-group-count">{{ g.list.length }} 条</span>
        <span class="muted w-group-hint">{{ st(g).open ? '点击折叠' : '点击展开' }}</span>
        <span class="w-group-arrow">{{ st(g).open ? '▾' : '▸' }}</span>
      </div>
      <template v-if="st(g).open">
        <div v-for="w in st(g).full ? g.list : g.list.slice(0, PREVIEW)" :key="w.id" class="w-card">
          <div class="w-head-row">
            <el-tag type="danger" size="small">错 {{ w.wrong_count }} 次</el-tag>
            <el-tag type="info" size="small" style="margin-left: 6px">{{ w.kp_title || '未关联' }}</el-tag>
            <el-tag v-if="w.review_marked" type="warning" size="small" style="margin-left: 6px">
              待重点复习
            </el-tag>
            <el-tag v-if="w.correct_streak" type="success" size="small" style="margin-left: 6px">
              已连对 {{ w.correct_streak }}/2
            </el-tag>
            <el-tag v-if="w.error_type" type="warning" size="small" effect="plain" style="margin-left: 6px">
              错因：{{ w.error_type }}
            </el-tag>
            <el-tooltip v-if="w.srs_interval_text" :content="srsTip(w)" placement="top">
              <el-tag
                :type="w.srs_due ? 'danger' : 'primary'"
                size="small"
                effect="plain"
                style="margin-left: 6px"
              >
                {{ w.srs_interval_text }}
              </el-tag>
            </el-tooltip>
            <span class="w-date muted">{{ w.last_wrong_at }}</span>
          </div>
          <div class="w-question">{{ w.question }}</div>
          <div class="w-answer">参考答案：{{ w.answer }}</div>
          <div class="w-actions">
            <el-button size="small" @click="markReview(w)">
              {{ w.review_marked ? '取消重点标记' : '标记重点复习' }}
            </el-button>
            <el-button size="small" type="success" @click="resolve(w)">标记已掌握</el-button>
          </div>
        </div>
        <el-button
          v-if="!st(g).full && g.list.length > PREVIEW"
          size="small"
          text
          type="primary"
          @click="st(g).full = true"
        >
          展开本组其余 {{ g.list.length - PREVIEW }} 条
        </el-button>
        <el-button
          v-else-if="st(g).full && g.list.length > PREVIEW"
          size="small"
          text
          @click="st(g).full = false"
        >
          收起本组
        </el-button>
      </template>
    </div>
  </el-card>

  <AiInline context="错题本" />
</template>

<script setup>
import AiInline from '../components/AiInline.vue'
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const items = ref([])
const upcoming = ref([])
const dueCount = ref(0)
const view = ref('all')
const onlyUnresolved = ref(true)
const exporting = ref(false)
const gening = ref(false)

// ---------- 分组 + 折叠 ----------
// 按课程把错题分成四史 + 其他：默认只展开第一组、组内先露 3 条，
// 页面短到不滚动就能看到底部的 AI 对话框（这是内嵌 AI 上线后用户提的最痛点）
const PREVIEW = 3
const COURSE_ORDER = [
  ['party', '党史', 'danger'],
  ['prc', '新中国史', 'warning'],
  ['reform', '改革开放史', 'success'],
  ['socialism', '社会主义发展史', 'primary'],
]
// course 列历史上有两套写法（英文 track / 中文课程名），都归到同一个桶
const COURSE_ALIAS = {
  党史: 'party', 中国党史: 'party', 新中国史: 'prc', 中华人民共和国史: 'prc',
  改革开放史: 'reform', 社会主义发展史: 'socialism',
}

function bucketOf(w) {
  const c = String(w.course || '').trim().toLowerCase()
  if (COURSE_ALIAS[c]) return COURSE_ALIAS[c]
  return ['party', 'prc', 'reform', 'socialism'].includes(c) ? c : 'other'
}

const groups = computed(() => {
  if (view.value === 'due') {
    return [{ key: 'due', name: '今日到期', tag: 'danger', list: items.value }]
  }
  const map = { party: [], prc: [], reform: [], socialism: [], other: [] }
  for (const w of items.value) map[bucketOf(w)].push(w)
  return [
    ...COURSE_ORDER.map(([key, name, tag]) => ({ key, name, tag, list: map[key] })),
    { key: 'other', name: '其他 / 未分类', tag: 'info', list: map.other },
  ].filter((g) => g.list.length)
})

// 每组的展开状态：默认只开第一组；今日复习视图整组全量展示
const gstate = ref({})
function st(g) {
  if (!gstate.value[g.key]) {
    gstate.value[g.key] = {
      open: view.value === 'due' || groups.value[0]?.key === g.key,
      full: view.value === 'due',
    }
  }
  return gstate.value[g.key]
}

// 今日队列为空时的提示语：告诉学生下一次该什么时候来
const dueHint = computed(() => {
  if (!upcoming.value.length) return '错题本里没有未掌握的内容'
  const next = upcoming.value[0]
  return `最近一条${next.srs_interval_text}（${next.kp_title || '未关联'}），到点再来`
})

// 把 FSRS 的稳定度/难度翻成人话，鼠标悬停时看
function srsTip(w) {
  const parts = []
  if (w.srs_stability) parts.push(`记忆稳定度 ${w.srs_stability} 天`)
  if (w.srs_difficulty) parts.push(`难度 ${w.srs_difficulty}/10`)
  if (w.srs_retrievability != null) {
    parts.push(`当前记得的概率约 ${Math.round(w.srs_retrievability * 100)}%`)
  }
  return parts.length ? parts.join(' · ') : '按间隔复习算法自动排期'
}

// 错因归因交给 AI 对话页：那边能看题、能写 error_type，还能连着聊
function aiDiagnose() {
  router.push({
    path: '/ai',
    query: {
      q: '帮我看看错题本里这些题为什么老错：逐题判断错因并用 tag_wrong_error 打上标签，最后按错因给我 2-3 条改法',
    },
  })
}

async function genSimilar() {
  gening.value = true
  try {
    const r = await api.generatePersonal({ num: 5 })
    ElMessage.success(`已按 ${r.based_on_wrong} 条错题生成 ${r.generated} 道题，去「自测」页做`)
  } catch (e) {
    ElMessage.warning(e.message || '错题本里还没有未掌握的题')
  } finally {
    gening.value = false
  }
}

async function load() {
  gstate.value = {} // 视图切换后分组状态重置，避免残留的展开/折叠错位
  try {
    if (view.value === 'due') {
      const r = await api.reviewDue(50)
      items.value = r.items || []
      upcoming.value = r.upcoming || []
      dueCount.value = r.due_count || 0
    } else {
      items.value = await api.wrongBook(onlyUnresolved.value)
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// 导出永远导全部错题（含已掌握），导未掌握的容易漏
async function doExportCsv() {
  exporting.value = true
  try {
    await api.exportWrongCsv(false)
    ElMessage.success('CSV 已下载')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    exporting.value = false
  }
}

function doPrint() {
  api.openWrongPrint(false)
  ElMessage.info('已在新标签页打开，按 Ctrl+P 选择「另存为 PDF」')
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
.wb-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.wb-head-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.wb-head-right { display: flex; align-items: center; gap: 12px; }
.w-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.w-head-row { display: flex; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 4px 0; }
.w-date { margin-left: auto; }
.w-question { font-weight: 600; margin-bottom: 6px; }
.w-answer { color: #67c23a; margin-bottom: 10px; }
.w-actions { display: flex; gap: 8px; }

@media (max-width: 768px) {
  .wb-head-right { width: 100%; justify-content: flex-end; }
  .w-date { width: 100%; margin-left: 0; }
}

/* 分组头：点击整行切换折叠 */
.w-group { margin-bottom: 6px; }
.w-group-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 6px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px dashed #ebeef5;
  margin-bottom: 10px;
}
.w-group-count { font-size: 13px; }
.w-group-hint { font-size: 12px; margin-left: auto; }
.w-group-arrow { color: #909399; font-size: 14px; }
</style>
