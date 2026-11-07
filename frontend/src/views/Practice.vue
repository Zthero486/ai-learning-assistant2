<template>
  <div class="practice-page">
    <!-- ============ 阶段一：组卷 ============ -->
    <el-card v-if="stage === 'setup'" class="page-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">开始练习</span>
          <el-button type="warning" plain :loading="gening" @click="genPersonal">
            AI 错题专项 · 出 5 道新题
          </el-button>
        </div>
      </template>

      <!-- 今日目标：参考多邻国的每日目标条，让人有「今天还没打卡」的念头 -->
      <div class="today-box">
        <div class="today-line">
          <span class="today-label">今日已练 <b>{{ sum.today_total }}</b> / {{ DAILY_GOAL }} 题</span>
          <span v-if="sum.today_total" class="today-rate">今日正确率 {{ todayRate }}%</span>
        </div>
        <el-progress
          :percentage="Math.min(100, Math.round((sum.today_total / DAILY_GOAL) * 100))"
          :stroke-width="10"
          :show-text="false"
          :color="sum.today_total >= DAILY_GOAL ? '#67c23a' : '#409eff'"
        />
      </div>

      <div class="stat-row">
        <div class="stat"><b>{{ sum.total }}</b><span>题库存量</span></div>
        <div class="stat warn"><b>{{ sum.active_wrong }}</b><span>待攻克错题</span></div>
        <div class="stat ok"><b>{{ sum.mastered }}</b><span>已掌握</span></div>
      </div>

      <el-divider />

      <div class="setup-form">
        <div class="form-row">
          <span class="form-label">练什么</span>
          <el-radio-group v-model="range">
            <el-radio-button value="all">全部题库</el-radio-button>
            <el-radio-button value="wrong">错题优先</el-radio-button>
            <el-radio-button value="kp">按知识点</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="range === 'kp'" class="form-row">
          <span class="form-label">选知识点</span>
          <el-select v-model="kpPick" filterable placeholder="选择知识点" style="width:320px">
            <el-option v-for="k in kps" :key="k.id" :label="k.title" :value="k.id" />
          </el-select>
        </div>
        <div class="form-row">
          <span class="form-label">一轮几题</span>
          <el-radio-group v-model="size">
            <el-radio-button :value="5">5 题 · 约 3 分钟</el-radio-button>
            <el-radio-button :value="10">10 题 · 约 6 分钟</el-radio-button>
            <el-radio-button :value="15">15 题 · 约 10 分钟</el-radio-button>
          </el-radio-group>
        </div>
        <div class="form-row">
          <el-button type="primary" size="large" :disabled="!poolFor(range).length" @click="start">
            开始这一轮（共 {{ poolFor(range).length }} 题可选）
          </el-button>
          <span v-if="!poolFor(range).length" class="muted-tip">
            这个范围还没有题：点右上「AI 错题专项」，或去「史实要点」页对知识点点「AI 出题」
          </span>
        </div>
      </div>
    </el-card>

    <!-- ============ 阶段二：一次一题（Anki / 多邻国式） ============ -->
    <el-card v-else-if="stage === 'session'" class="page-card session-card">
      <div class="sess-top">
        <el-button text size="small" @click="quitSession">提前结束</el-button>
        <span class="sess-count">第 {{ idx + 1 }} / {{ list.length }} 题</span>
        <span class="sess-score">
          <span class="s-ok">✓ {{ okCount }}</span>
          <span class="s-no">✗ {{ noCount }}</span>
        </span>
      </div>
      <el-progress
        :percentage="Math.round(((idx + (judged ? 1 : 0)) / list.length) * 100)"
        :stroke-width="8" :show-text="false"
      />

      <div class="q-stage">
        <div class="q-tags">
          <el-tag size="small" :type="q.source === 'ai' ? 'warning' : 'info'" effect="plain">
            {{ q.source === 'ai' ? 'AI 题' : '规则题' }}
          </el-tag>
          <el-tag size="small" effect="plain">{{ typeName(q) }}</el-tag>
          <el-tag v-if="q.kp_title" size="small" type="info" effect="plain">{{ q.kp_title }}</el-tag>
          <el-tag v-if="isWrongQ(q)" size="small" type="danger" effect="plain">错题重现</el-tag>
        </div>
        <div class="q-text">{{ q.question }}</div>

        <!-- 客观题：选项按钮，点选即判（即时反馈） -->
        <div v-if="options" class="opt-list">
          <button
            v-for="o in options" :key="o.key"
            class="opt-btn"
            :class="{
              picked: picked === o.key,
              right: judged && o.key === answerKey,
              wrong: judged && picked === o.key && picked !== answerKey,
            }"
            :disabled="judged"
            @click="pick(o)"
          >
            <span class="opt-key">{{ o.key }}</span>
            <span class="opt-text">{{ o.text }}</span>
          </button>
        </div>

        <!-- 主观题：写答案 → 对照参考答案 → 自评两键（Anki 式） -->
        <template v-else>
          <div v-if="!judged" class="self-input">
            <el-input
              v-model="draft" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="写下你的答案（写完对照参考答案，自己判对错）"
              @keydown.enter.ctrl="revealSelf"
            />
            <el-button type="primary" :disabled="!draft.trim()" @click="revealSelf">
              对照参考答案
            </el-button>
          </div>
        </template>

        <!-- 参考答案 + 自评（主观题判分前） -->
        <div v-if="judged && !options" class="ref-answer">
          <div class="ra-label">参考答案</div>
          <div class="ra-body">{{ q.answer }}</div>
          <div v-if="draft.trim()" class="ra-mine">你的答案：{{ draft.trim() }}</div>
          <div v-if="lastCorrect === null" class="self-judge">
            <span>对照一下，这道题你——</span>
            <el-button type="success" @click="selfJudge(true)">答对了 ✓</el-button>
            <el-button type="danger" plain @click="selfJudge(false)">答错了 ✗</el-button>
          </div>
        </div>

        <!-- 判分结果 + FSRS 排期提示 -->
        <div v-if="lastCorrect !== null" :class="['verdict', lastCorrect ? 'v-ok' : 'v-no']">
          <span class="v-icon">{{ lastCorrect ? '✓' : '✗' }}</span>
          <div class="v-body">
            <div class="v-line">{{ lastCorrect ? '答对了 ✓' : '答错了，已记入错题本' }}</div>
            <div v-if="schedText" class="v-sched">{{ schedText }}</div>
          </div>
        </div>

        <div v-if="lastCorrect !== null" class="next-row">
          <el-checkbox v-model="autoNext" size="small">自动下一题</el-checkbox>
          <el-button type="primary" size="large" @click="next">
            {{ idx + 1 >= list.length ? '看本轮成绩 →' : '下一题 →' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- ============ 阶段三：结算（成绩单） ============ -->
    <el-card v-else class="page-card result-card">
      <div class="result-hero">
        <div class="ring" :class="rate >= 80 ? '' : rate >= 60 ? 'ring-mid' : 'ring-bad'">
          <span class="ring-num">{{ rate }}%</span>
          <span class="ring-cap">正确率</span>
        </div>
        <div class="result-side">
          <div class="rs-line">本轮共 <b>{{ doneCount }}</b> 题 · 答对 <b class="c-ok">{{ okCount }}</b> · 答错 <b class="c-no">{{ noCount }}</b></div>
          <div class="rs-line">用时 {{ elapsedText }}{{ todayLine }}</div>
          <div class="rs-cheer">{{ cheer }}</div>
        </div>
      </div>

      <template v-if="noCount">
        <el-divider>答错的题已自动进错题本，按排期回来重做</el-divider>
        <div v-for="w in wrongOnes" :key="w.id" class="wrong-item">
          <span class="wi-text">{{ w.question }}</span>
          <span class="wi-ans">答：{{ w.answer }}</span>
        </div>
      </template>

      <div class="result-actions">
        <el-button type="primary" size="large" @click="backToSetup">再来一轮</el-button>
        <el-button size="large" @click="goWrongBook">去错题本复盘</el-button>
      </div>
    </el-card>

    <!-- ============ 题库浏览（只读收纳；做题请走上面的练习模式） ============ -->
    <el-card class="page-card" style="margin-top:14px">
      <el-collapse>
        <el-collapse-item :title="`题库浏览（只读，共 ${questions.length} 题）`">
          <div v-for="(qq, i) in questions" :key="qq.id" class="q-card">
            <div class="q-head">
              <el-tag size="small" :type="qq.source === 'ai' ? 'warning' : 'info'" effect="plain">
                {{ qq.source === 'ai' ? 'AI 题' : '规则题' }}
              </el-tag>
              <el-tag size="small" type="info" effect="plain">{{ qq.kp_title || '未关联' }}</el-tag>
              <span class="q-text">{{ i + 1 }}. {{ qq.question }}</span>
            </div>
            <div class="q-ans">参考答案：{{ qq.answer }}</div>
          </div>
          <el-empty v-if="!questions.length" description="还没有题目：点上方「AI 错题专项」，或去「史实要点」页对知识点点「AI 出题」" />
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>

  <AiInline context="自测" />
</template>

<script setup>
import AiInline from '../components/AiInline.vue'
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const DAILY_GOAL = 10 // 每日目标：做满 10 题，进度条走满

const router = useRouter()
const route = useRoute()
const stage = ref('setup') // setup | session | result
const sum = ref({ total: 0, today_total: 0, today_correct: 0, active_wrong: 0, mastered: 0 })
const questions = ref([])
const kps = ref([])
const wrongQids = ref(new Set()) // 活跃错题的 question_id：错题优先组卷 + 「错题重现」标记
const gening = ref(false)

// 组卷设置
const range = ref('all')
const kpPick = ref(null)
const size = ref(10)

// 会话状态
const list = ref([])
const idx = ref(0)
const draft = ref('')
const picked = ref(null)
const judged = ref(false)       // 已亮出参考答案 / 客观题已作答
const lastCorrect = ref(null)   // null=待自评；true/false=已判
const okCount = ref(0)
const noCount = ref(0)
const schedText = ref('')
const autoNext = ref(true)
const startedAt = ref(0)
const finishedAt = ref(0)
const sessionWrong = ref([])    // 本轮答错的题，结算页展示
const doneCount = ref(0)

const q = computed(() => list.value[idx.value] || {})
const todayRate = computed(() =>
  sum.value.today_total ? Math.round((sum.value.today_correct / sum.value.today_total) * 100) : 0,
)
const rate = computed(() =>
  doneCount.value ? Math.round((okCount.value / doneCount.value) * 100) : 0,
)
const elapsedText = computed(() => {
  const s = Math.max(1, Math.round((finishedAt.value - startedAt.value) / 1000))
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`
})
const todayLine = computed(() =>
  sum.value.today_total ? `；今天累计 ${sum.value.today_total} 题` : '',
)
const cheer = computed(() => {
  if (rate.value >= 90) return '太稳了，这个考点可以翻篇了 🎉'
  if (rate.value >= 70) return '不错，错的那几道过两天按排期再战'
  if (rate.value >= 50) return '有点感觉了，错的题可以去问 AI「为什么错」'
  return '别灰心，错题本已经排好复习计划，按提示回来重做就行'
})
const wrongOnes = computed(() => sessionWrong.value)
// ---------- 数据加载 ----------
async function load() {
  try {
    ;[questions.value, kps.value, sum.value] = await Promise.all([
      api.listQuestions(),
      api.listKps(),
      api.practiceSummary(),
    ])
    try {
      const wrongs = await api.listWrong()
      wrongQids.value = new Set((wrongs || []).filter((w) => !w.resolved).map((w) => w.question_id))
    } catch { /* 错题本拉不到不影响练习 */ }
  } catch (e) {
    ElMessage.error(e.message)
  }
  tryStartFresh() // 若 AI 跳转已发生而题库刚加载完，这里补上
}

function poolFor(mode) {
  if (mode === 'kp') {
    return kpPick.value ? questions.value.filter((x) => x.kp_id === kpPick.value) : []
  }
  return questions.value
}

function isWrongQ(x) {
  return wrongQids.value.has(x.id)
}

// ---------- 组卷 ----------
function shuffle(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function start() {
  let pool
  if (range.value === 'wrong') {
    // 错题优先：活跃错题打乱排前面，不够的用新题补
    const w = shuffle(questions.value.filter(isWrongQ))
    const rest = shuffle(questions.value.filter((x) => !isWrongQ(x)))
    pool = [...w, ...rest]
  } else {
    pool = shuffle(poolFor(range.value))
  }
  if (!pool.length) return
  beginSession(shuffle(pool).slice(0, Math.min(size.value, pool.length)))
}

function beginSession(pool) {
  list.value = pool
  idx.value = 0
  okCount.value = 0
  noCount.value = 0
  doneCount.value = 0
  sessionWrong.value = []
  startedAt.value = Date.now()
  enterQuestion()
  stage.value = 'session'
}

// ---------- AI 联动：出题后直接开一轮「AI 新题」作答，数据落库 ----------
// AI 出题工具跳转时带 ?fresh=<question_ids逗号分隔>：等题库加载完就抽这几道题直接开做
let pendingFresh = null
watch(() => route.query.fresh, (v) => {
  if (!v) return
  pendingFresh = String(v)
  router.replace({ query: {} }) // 立即清标记，刷新不会重复弹
  tryStartFresh()
})

function tryStartFresh() {
  if (!pendingFresh || !questions.value.length) return // 题库还没加载完就等 load() 回调
  const want = pendingFresh.split(',').map(Number).filter(Boolean)
  pendingFresh = null
  if (!want.length) return
  const picked = want.map((id) => questions.value.find((x) => x.id === id)).filter(Boolean)
  if (!picked.length) {
    ElMessage.warning('AI 刚出的题还没同步到题库，稍后手动组卷即可')
    return
  }
  beginSession(picked)
  ElMessage.success(`AI 新题来啦，共 ${picked.length} 道，直接开始作答（答错自动进错题本）`)
}

function enterQuestion() {
  draft.value = ''
  picked.value = null
  judged.value = false
  lastCorrect.value = null
  schedText.value = ''
}

function quitSession() {
  clearTimeout(nextTimer)
  nextTimer = null
  if (!doneCount.value) {
    stage.value = 'setup' // 一题没做直接返回，不算成绩
    return
  }
  finish() // 做了一半退出也给结算，不白做
}

// ---------- 题型解析 ----------
// 单选题的选项长在题干里（AI 出题惯例：…？A. xx B. xx C. xx D. xx），解析成按钮。
// 认不出来的题型一律回退到「输入 + 自评」，不会误判。
function parseOptions(text) {
  // 前导放宽到「非字母数字」：全角括号/问号/引号后面都可能直接跟 A. （实测「）A.」「？A.」）
  const re = /(^|[^A-Za-z0-9])([A-D])\s*[.、．)）：:]\s*/g
  const marks = []
  let m
  while ((m = re.exec(text)) !== null) {
    marks.push({ key: m[2], leadStart: m.index, start: m.index + m[0].length })
  }
  // 找最长的连续 A,B,C(,D) 标记段（至少 3 项才算选择题）
  let best = null
  for (let i = 0; i < marks.length; i++) {
    if (marks[i].key !== 'A') continue
    const seq = [marks[i]]
    for (let j = i + 1; j < marks.length && seq.length < 4; j++) {
      if (marks[j].key === String.fromCharCode(65 + seq.length)) seq.push(marks[j])
      else break
    }
    if (seq.length >= 3 && (!best || seq.length > best.length)) best = seq
  }
  if (!best) return null
  return best.map((s, i) => {
    const end = i + 1 < best.length ? best[i + 1].leadStart : text.length
    return { key: s.key, text: text.slice(s.start, end).trim() }
  })
}

const options = computed(() => {
  if (!q.value.question || !answerKey.value) return null // 答案不以字母开头就不用按钮，防误判
  return parseOptions(q.value.question)
})

// 参考答案以 A-D 字母开头才算客观题（"B" / "B. xxx" 都行）
const answerKey = computed(() => {
  const a = (q.value.answer || '').trim().toUpperCase()
  const m = a.match(/^([A-D])(\s|[.、．)）：:]|$)/)
  return m ? m[1] : null
})

function typeName(x) {
  const t = (x.type || '').toLowerCase()
  if (t.includes('单选') || t.includes('choice') || t.includes('single')) return '单选题'
  if (t.includes('多选') || t.includes('multi')) return '多选题'
  if (t.includes('判断') || t.includes('judge')) return '判断题'
  if (t.includes('排序') || t.includes('order')) return '排序题'
  if (t.includes('材料') || t.includes('分析')) return '材料分析'
  return '简答题'
}

// ---------- 作答与判分 ----------
async function record(correct, answerText) {
  try {
    const r = await api.submitPractice({ question_id: q.value.id, answer: answerText, correct })
    const sched = (r && r.schedule) || {}
    if (correct && r && r.wrong_book && r.wrong_book.resolved) {
      schedText.value = '这道错题已经掌握，移出错题本 🎉'
    } else {
      schedText.value = sched.interval_text ? `${sched.interval_text}后再来复习` : ''
    }
  } catch (e) {
    schedText.value = ''
    ElMessage.error(e.message)
  }
}

// 自动下一题的定时器：手点「下一题」或提前结束时必须取消，否则会连跳两题
let nextTimer = null
function scheduleNext(ms) {
  clearTimeout(nextTimer)
  nextTimer = setTimeout(() => {
    nextTimer = null
    next()
  }, ms)
}

async function pick(o) {
  if (judged.value) return
  picked.value = o.key
  judged.value = true
  settle(o.key === answerKey.value, `${o.key}. ${o.text}`)
  if (autoNext.value) scheduleNext(1400)
}

function revealSelf() {
  if (judged.value || !draft.value.trim()) return
  judged.value = true // 亮出参考答案，等学生自评
}

async function selfJudge(correct) {
  if (lastCorrect.value !== null) return
  settle(correct, draft.value.trim())
  if (autoNext.value) scheduleNext(1500)
}

function settle(correct, answerText) {
  lastCorrect.value = correct
  doneCount.value++
  if (correct) okCount.value++
  else {
    noCount.value++
    sessionWrong.value.push(q.value)
  }
  record(correct, answerText) // 异步落库，不阻塞下一题
}

async function next() {
  clearTimeout(nextTimer)
  nextTimer = null
  if (stage.value !== 'session') return
  if (idx.value + 1 >= list.value.length) {
    finish()
    return
  }
  idx.value++
  enterQuestion()
}

function finish() {
  finishedAt.value = Date.now()
  stage.value = 'result'
  load() // 刷新今日进度与错题存量
}

function backToSetup() {
  stage.value = 'setup'
}

function goWrongBook() {
  router.push('/wrong-book')
}

// ---------- AI 错题专项 ----------
async function genPersonal() {
  gening.value = true
  try {
    const r = await api.generatePersonal({ num: 5 })
    ElMessage.success(`已按 ${r.based_on_wrong} 条错题生成 ${r.generated} 道针对性题，已进题库`)
    await load()
  } catch (e) {
    ElMessage.warning(e.message || '错题本里还没有未掌握的题')
  } finally {
    gening.value = false
  }
}

onMounted(() => {
  load().then(() => {
    // AI 联动跳转过来（出完题自动带你看）：直接开做新题
    if (route.query.fresh) {
      pendingFresh = String(route.query.fresh)
      router.replace({ query: {} })
      tryStartFresh()
    }
  })
})
</script>

<style scoped>
.practice-page { max-width: 860px; }
.card-head { display: flex; gap: 10px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.card-title { font-weight: 700; font-size: 16px; }

/* 今日目标条 */
.today-box { background: #f0f7ff; border-radius: 10px; padding: 14px 16px; }
.today-line { display: flex; justify-content: space-between; margin-bottom: 8px; }
.today-label b { color: #409eff; }
.today-rate { color: #67c23a; font-size: 13px; }

/* 库概况 */
.stat-row { display: flex; gap: 12px; margin-top: 14px; }
.stat { flex: 1; background: #fafafa; border: 1px solid #ebeef5; border-radius: 10px; padding: 12px; text-align: center; }
.stat b { display: block; font-size: 24px; }
.stat span { color: #909399; font-size: 12px; }
.stat.warn b { color: #e6a23c; }
.stat.ok b { color: #67c23a; }

.setup-form { display: flex; flex-direction: column; gap: 16px; }
.form-row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.form-label { width: 70px; color: #606266; font-size: 14px; }
.muted-tip { color: #909399; font-size: 13px; }

/* 会话 */
.session-card :deep(.el-card__body) { padding-top: 10px; }
.sess-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sess-count { font-weight: 600; }
.sess-score { display: flex; gap: 10px; }
.s-ok { color: #67c23a; font-weight: 700; }
.s-no { color: #f56c6c; font-weight: 700; }

.q-stage { margin-top: 18px; }
.q-tags { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.q-text { font-size: 17px; font-weight: 600; line-height: 1.7; margin-bottom: 18px; white-space: pre-wrap; }

/* 选项按钮 */
.opt-list { display: flex; flex-direction: column; gap: 10px; }
.opt-btn {
  display: flex; gap: 12px; align-items: flex-start; text-align: left;
  border: 1.5px solid #dcdfe6; background: #fff; border-radius: 10px;
  padding: 12px 14px; font-size: 15px; line-height: 1.6; cursor: pointer;
  transition: all 0.15s;
}
.opt-btn:hover:not(:disabled) { border-color: #409eff; background: #f0f7ff; }
.opt-btn.picked { border-color: #409eff; }
.opt-btn.right { border-color: #67c23a; background: #f0f9eb; }
.opt-btn.wrong { border-color: #f56c6c; background: #fef0f0; }
.opt-btn:disabled { cursor: default; }
.opt-key {
  flex: none; width: 26px; height: 26px; border-radius: 50%;
  background: #f0f2f5; color: #606266; font-weight: 700;
  display: flex; align-items: center; justify-content: center; font-size: 13px;
}
.opt-btn.right .opt-key { background: #67c23a; color: #fff; }
.opt-btn.wrong .opt-key { background: #f56c6c; color: #fff; }

/* 主观题 */
.self-input { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.ref-answer { background: #f0f9eb; border-radius: 10px; padding: 12px 14px; margin-top: 12px; }
.ra-label { font-size: 12px; color: #67c23a; font-weight: 700; margin-bottom: 4px; }
.ra-body { line-height: 1.7; white-space: pre-wrap; }
.ra-mine { margin-top: 8px; color: #909399; font-size: 13px; }
.self-judge { display: flex; gap: 10px; align-items: center; margin-top: 12px; font-size: 14px; }

/* 判分反馈 */
.verdict { display: flex; gap: 10px; align-items: flex-start; border-radius: 10px; padding: 12px 14px; margin-top: 14px; }
.v-ok { background: #f0f9eb; }
.v-no { background: #fef0f0; }
.v-icon { font-size: 20px; font-weight: 800; }
.v-ok .v-icon { color: #67c23a; }
.v-no .v-icon { color: #f56c6c; }
.v-line { font-weight: 600; }
.v-sched { color: #909399; font-size: 13px; margin-top: 2px; }

.next-row { display: flex; justify-content: flex-end; align-items: center; gap: 14px; margin-top: 18px; }

/* 结算 */
.result-hero { display: flex; gap: 26px; align-items: center; padding: 10px 6px; }
.ring {
  flex: none; width: 130px; height: 130px; border-radius: 50%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 8px solid #67c23a; color: #67c23a;
}
.ring-mid { border-color: #e6a23c; color: #e6a23c; }
.ring-bad { border-color: #f56c6c; color: #f56c6c; }
.ring-num { font-size: 30px; font-weight: 800; }
.ring-cap { font-size: 12px; }
.result-side .rs-line { margin-bottom: 8px; }
.rs-line b { font-size: 17px; }
.c-ok { color: #67c23a; }
.c-no { color: #f56c6c; }
.rs-cheer { color: #606266; }
.wrong-item { border-left: 3px solid #f56c6c; padding: 8px 12px; margin-bottom: 10px; background: #fafafa; border-radius: 0 8px 8px 0; }
.wi-text { display: block; font-weight: 600; line-height: 1.6; }
.wi-ans { color: #67c23a; font-size: 13px; }
.result-actions { display: flex; justify-content: center; gap: 14px; margin-top: 20px; }

/* 题库浏览 */
.q-card { border-bottom: 1px dashed #ebeef5; padding: 12px 2px; }
.q-card:last-child { border-bottom: none; }
.q-head { display: flex; gap: 6px; align-items: baseline; }
.q-text { margin-left: 6px; font-weight: 600; line-height: 1.6; }
.q-ans { margin-top: 6px; color: #67c23a; font-size: 13px; padding-left: 4px; }
</style>
