<template>
  <div v-loading="loading">
    <div class="page-head">
      <div>
        <h2 class="title">{{ data.track_name }} · 教材目录</h2>
        <div class="muted">
          {{ data.chapter_count }} 章 {{ data.section_count }} 节 · 教材正文 {{ charText }} ·
          知识点 {{ data.total_kp }} 个 · 题目 {{ data.total_q }} 道
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
              <span class="text-dot" v-if="ch.chars" title="有教材正文"></span>
              <span class="chapter-stat" v-if="ch.kp">{{ ch.kp }}</span>
            </div>
            <div v-show="opened.includes(ch.code)" class="sections">
              <div
                class="section chapter-text"
                :class="{ active: ch.code === active }"
                @click="pick(ch.code)"
              >
                <span class="sec-title">本章正文</span>
                <span class="sec-chars">{{ ch.chars ? ch.chars + ' 字' : '暂无' }}</span>
              </div>
              <div
                v-for="s in ch.sections"
                :key="s.code"
                class="section"
                :class="{ active: s.code === active }"
                @click="pick(s.code)"
              >
                <span class="text-dot sm" v-if="s.chars"></span>
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

          <!-- 教材正文 -->
          <div class="text-block">
            <div class="block-head text-head">
              <span>教材正文 <em v-if="node.content" class="text-count">{{ node.content.length }} 字</em>
                <em v-if="notes.length" class="text-count note-count">· 笔记 {{ notes.length }}</em>
              </span>
              <div class="text-tools" v-if="node.content">
                <el-button link size="small" @click="fontStep(-1)">A-</el-button>
                <el-button link size="small" @click="fontStep(1)">A+</el-button>
                <el-button link size="small" @click="textOpen = !textOpen">
                  {{ textOpen ? '收起' : '展开全文' }}
                </el-button>
              </div>
            </div>
            <div
              v-if="node.content"
              v-show="textOpen"
              ref="textBody"
              class="text-body"
              :style="{ fontSize: fontSize + 'px' }"
              @mouseup="onSelectEnd"
              @touchend="onSelectEnd"
              @scroll="selBar.show = false"
            >
              <p v-for="(p, i) in renderedParas" :key="i" :data-pi="i">
                <template v-for="(seg, j) in p.segs" :key="j">
                  <mark
                    v-if="seg.note"
                    :class="['mk', 'c-' + seg.note.color]"
                    @click.stop="openNote(seg.note, $event)"
                  >{{ seg.t }}</mark>
                  <template v-else>{{ seg.t }}</template>
                </template>
              </p>
              <div v-if="!notes.length" class="text-hint">划选正文可高亮或写批注，点击已有高亮可编辑</div>
            </div>
            <div v-else class="text-missing">
              本节正文还没切分出来（教材是扫描版，个别页序错乱）。可以先看「本章正文」，
              或者用下面的知识点和自测复习。
            </div>
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

  <AiInline context="教材目录" />

  <!-- 划词浮动工具条（fixed 定位） -->
  <div
    v-if="selBar.show"
    class="sel-bar"
    :style="{ left: selBar.x + 'px', top: selBar.y + 'px' }"
  >
    <span
      v-for="c in USER_COLORS"
      :key="c"
      class="sel-dot"
      :style="{ background: NOTE_COLORS[c] }"
      :title="'高亮：' + c"
      @mousedown.prevent="saveSelection(c, false)"
      @touchstart.prevent="saveSelection(c, false)"
    ></span>
    <span class="sel-btn" @mousedown.prevent="saveSelection('yellow', true)" @touchstart.prevent="saveSelection('yellow', true)">批注</span>
    <span class="sel-btn" @mousedown.prevent="selBar.show = false" @touchstart.prevent="selBar.show = false">✕</span>
  </div>

  <!-- 笔记编辑弹窗 -->
  <el-dialog v-model="noteDlg" title="教材笔记" width="420px">
    <div class="note-quote">「{{ noteForm.quote }}」</div>
    <el-input
      v-model="noteForm.note"
      type="textarea"
      :rows="3"
      maxlength="2000"
      placeholder="批注内容（可留空，只改高亮颜色）"
    />
    <div class="color-row">
      <span
        v-for="c in dlgColors"
        :key="c"
        class="sel-dot big"
        :class="{ on: noteForm.color === c }"
        :style="{ background: NOTE_COLORS[c] }"
        @click="noteForm.color = c"
      ></span>
    </div>
    <template #footer>
      <el-button type="danger" plain @click="removeNote">删除</el-button>
      <el-button type="primary" :loading="saving" @click="saveNoteEdit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import AiInline from '../components/AiInline.vue'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import api, { auth } from '../api'

const route = useRoute()
const loading = ref(true)
const data = ref({ chapters: [], chapter_count: 0, section_count: 0, total_kp: 0, total_q: 0, total_chars: 0, track_name: '' })
const opened = ref([])
const active = ref('')
const node = ref(null)
const kpDlg = ref(false)
const saving = ref(false)
const form = reactive({ title: '', description: '', exam_type: 'recall' })
const textOpen = ref(true)
const fontSize = ref(Number(localStorage.getItem('kp_font') || 15))
const textBody = ref(null)
const notes = ref([])
const flash = ref(null) // ?hl= 带来的临时定位高亮（不落库）
const noteDlg = ref(false)
const noteForm = reactive({ id: 0, quote: '', note: '', color: 'yellow' })
const selBar = reactive({ show: false, x: 0, y: 0, quote: '', offset: 0, length: 0 })

const NOTE_COLORS = { yellow: '#ffe58f', green: '#b7eb8f', blue: '#91caff', pink: '#ffadd2', purple: '#d3adf7' }
const COLOR_HEX = { ...NOTE_COLORS, flash: '#ffc9c9' }
// 用户划词可用色（紫色是 AI 专属，不开放给手动划选）
const USER_COLORS = ['yellow', 'green', 'blue', 'pink']
// 笔记弹窗色板：当前是 AI 紫时多列一个紫，让用户能保持/改回
const dlgColors = computed(() =>
  noteForm.color === 'purple' ? [...USER_COLORS, 'purple'] : USER_COLORS)

const EXAM = { recall: '史实识记', sequence: '时序定位', argument: '史论结合', apply: '现实联系' }
const KIND = { meeting: '会议', event: '事件', document: '文件' }
const examLabel = (k) => EXAM[k] || k
const kindLabel = (k) => KIND[k] || '事件'

const charText = computed(() => {
  const n = data.value.total_chars || 0
  if (!n) return '未入库'
  return n > 10000 ? `${(n / 10000).toFixed(1)} 万字` : `${n} 字`
})

const renderedParas = computed(() => {
  const content = node.value?.content || ''
  if (!content) return []
  // 高亮区间（含 ?hl= 的临时定位）合并进段落后切块渲染
  const marks = notes.value.map((n) => ({ o: n.offset, l: n.length, note: n }))
  if (flash.value) marks.push({ o: flash.value.offset, l: flash.value.length, note: { id: 0, color: 'flash' } })
  // 同起点时 flash（AI 带来的临时定位）排前面 —— 下面“重叠丢弃后到者”否则会
  // 把 flash 丢掉，学生点了 AI 的原文定位却什么都看不到（真机实测踩过）
  marks.sort((a, b) => a.o - b.o || (a.note.color === 'flash' ? -1 : b.note.color === 'flash' ? 1 : 0))
  const merged = []
  for (const m of marks) {
    const last = merged[merged.length - 1]
    if (last && m.o < last.o + last.l) continue // 重叠的高亮丢弃后到的（简单处理）
    merged.push(m)
  }
  const paras = []
  const re = /[^\n]+/g
  let m2
  while ((m2 = re.exec(content))) {
    let s = m2.index
    let e = m2.index + m2[0].length
    while (s < e && /\s/.test(content[s])) s++
    while (e > s && /\s/.test(content[e - 1])) e--
    if (e <= s) continue
    const segs = []
    let cur = s
    for (const mk of merged) {
      const ms = Math.max(mk.o, s)
      const me = Math.min(mk.o + mk.l, e)
      if (me <= ms) continue
      if (ms > cur) segs.push({ t: content.slice(cur, ms) })
      segs.push({ t: content.slice(ms, me), note: mk.note })
      cur = me
    }
    if (cur < e) segs.push({ t: content.slice(cur, e) })
    paras.push({ start: s, segs })
  }
  return paras
})

function fontStep(d) {
  fontSize.value = Math.min(22, Math.max(13, fontSize.value + d))
  localStorage.setItem('kp_font', String(fontSize.value))
}

watch(node, () => {
  textOpen.value = true
  flash.value = null
})

// ---- 教材笔记：加载 / 划词 / 编辑 ----
async function loadNotes(code) {
  try {
    notes.value = (await api.listNotes(code)).items
  } catch {
    notes.value = []
  }
}

function offsetInPara(pEl, textNode, nodeOffset) {
  if (!textNode || textNode.nodeType !== Node.TEXT_NODE) return -1
  let off = 0
  const w = document.createTreeWalker(pEl, NodeFilter.SHOW_TEXT)
  let n
  while ((n = w.nextNode())) {
    if (n === textNode) return off + nodeOffset
    off += n.textContent.length
  }
  return -1
}

function onSelectEnd() {
  // 移动端长按选区结束后稍等再取，避免拿到空选区
  setTimeout(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.rangeCount) { selBar.show = false; return }
    const quote = sel.toString()
    if (!quote || quote.replace(/\s+/g, '').length < 2) { selBar.show = false; return }
    const range = sel.getRangeAt(0)
    const sc = range.startContainer
    const pEl = (sc.nodeType === Node.TEXT_NODE ? sc.parentElement : sc)?.closest?.('p')
    const para = pEl ? renderedParas.value[Number(pEl.dataset.pi)] : null
    if (!para) { selBar.show = false; return }
    // 只支持单段内划选（跨段偏移换算不可靠）
    const ec = range.endContainer
    const pEl2 = (ec.nodeType === Node.TEXT_NODE ? ec.parentElement : ec)?.closest?.('p')
    if (pEl2 !== pEl) { selBar.show = false; ElMessage.info('一次只划选一段内的文字'); return }
    const local = offsetInPara(pEl, range.startContainer, range.startOffset)
    if (local < 0) { selBar.show = false; return }
    const offset = para.start + local
    selBar.quote = quote.trim()
    selBar.offset = offset
    selBar.length = quote.trim().length
    const rect = range.getBoundingClientRect()
    selBar.x = Math.min(Math.max(rect.left, 8), window.innerWidth - 210)
    selBar.y = Math.max(rect.top - 44, 8)
    selBar.show = true
  }, 60)
}

async function saveSelection(color, withNote) {
  let note = ''
  if (withNote) {
    try {
      const r = await ElMessageBox.prompt('给这段原文写点批注（留空则只做高亮）', '新笔记', {
        inputPlaceholder: '比如：这里的时间点爱考',
      })
      note = (r.value || '').trim()
    } catch {
      return // 用户取消
    }
  }
  try {
    const n = await api.createNote({
      node_code: active.value,
      offset: selBar.offset,
      length: selBar.length,
      quote: selBar.quote,
      note,
      color,
    })
    notes.value = [...notes.value, n].sort((a, b) => a.offset - b.offset)
    selBar.show = false
    window.getSelection()?.removeAllRanges()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openNote(n) {
  if (!n.id) return // 临时定位高亮不可编辑
  const full = notes.value.find((x) => x.id === n.id)
  if (!full) return
  noteForm.id = full.id
  noteForm.quote = full.quote
  noteForm.note = full.note
  noteForm.color = full.color
  noteDlg.value = true
}

async function saveNoteEdit() {
  saving.value = true
  try {
    const n = await api.updateNote(noteForm.id, { note: noteForm.note, color: noteForm.color })
    notes.value = notes.value.map((x) => (x.id === n.id ? n : x))
    noteDlg.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function removeNote() {
  try {
    await ElMessageBox.confirm('删除这条高亮/批注？', '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.deleteNote(noteForm.id)
    notes.value = notes.value.filter((x) => x.id !== noteForm.id)
    noteDlg.value = false
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ?hl= 原文定位：在正文里找这段话并临时高亮、滚动过去。
// 教材正文来自 OCR 扫描件（「公元巧 16 年」「托马斯。莫尔」），模型引用时会顺手纠错，
// 所以逐字匹配经常落空 —— 三级兜底：去空白 → 去标点 → 二元组相似度滑窗。
function diceCoeff(a, b) {
  if (a === b) return 1
  if (a.length < 2 || b.length < 2) return 0
  const bag = new Map()
  for (let i = 0; i < a.length - 1; i++) {
    const g = a.slice(i, i + 2)
    bag.set(g, (bag.get(g) || 0) + 1)
  }
  let hit = 0
  for (let i = 0; i < b.length - 1; i++) {
    const g = b.slice(i, i + 2)
    const c = bag.get(g)
    if (c) { hit++; bag.set(g, c - 1) }
  }
  return (2 * hit) / (a.length - 1 + b.length - 1)
}

function locateQuote(q) {
  const content = node.value?.content || ''
  if (!content || !q) return
  const build = (reStr) => {
    const re = new RegExp(reStr, 'g')
    const map = []
    let norm = ''
    for (let i = 0; i < content.length; i++) {
      if (!re.test(content[i])) { norm += content[i]; map.push(i) }
    }
    return { re, norm, map }
  }
  const slice = (b, idx, len) => ({
    offset: b.map[idx],
    end: b.map[Math.min(idx + len - 1, b.map.length - 1)] + 1,
  })
  const exact = (b) => {
    const nq = q.replace(b.re, '').slice(0, 120)
    if (!nq) return null
    const idx = b.norm.indexOf(nq)
    if (idx >= 0) return { ...slice(b, idx, nq.length), soft: false }
    // 前缀回退：句中 OCR/标点差异常见，用可定位的前缀先顶上
    for (let L = Math.min(nq.length, 24); L >= 12; L--) {
      const i2 = b.norm.indexOf(nq.slice(0, L))
      if (i2 >= 0) return { ...slice(b, i2, L), soft: false }
    }
    return null
  }
  const fuzzy = (b) => {
    const nq = q.replace(b.re, '').slice(0, 80)
    if (nq.length < 8) return null
    const len = Math.min(nq.length, b.norm.length)
    let best = -1
    let bestScore = 0
    const step = Math.max(4, Math.floor(len / 12))
    for (let i = 0; i + 8 <= b.norm.length; i += step) {
      const score = diceCoeff(nq, b.norm.slice(i, i + len))
      if (score > bestScore) { bestScore = score; best = i }
    }
    if (best < 0 || bestScore < 0.5) return null
    return { ...slice(b, best, len), soft: true, score: bestScore }
  }
  const plain = build('\\s')
  const punctFree = build('[\\p{P}\\p{S}\\s]')
  const found = exact(plain) || exact(punctFree) || fuzzy(punctFree)
  if (!found) {
    ElMessage.info('没有在本节正文里找到这段原文，可能出自其他节')
    return
  }
  if (found.soft) {
    // 相似度命中的窗口可能从半个词开始，扩到完整句子再标，读起来更清楚
    let s = found.offset
    let e = found.end
    const stop = /[。！？；\n]/
    let guard = 0
    while (s > 0 && !stop.test(content[s - 1]) && guard++ < 60) s--
    guard = 0
    while (e < content.length && !stop.test(content[e]) && guard++ < 60) e++
    found.offset = s
    found.end = e
    ElMessage.info('教材是扫描版，已按相似度定位到对应段落')
  }
  flash.value = { offset: found.offset, length: found.end - found.offset }
  nextTick(() => {
    const el = textBody.value?.querySelector('.mk.c-flash')
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function toggle(code) {
  const i = opened.value.indexOf(code)
  if (i >= 0) opened.value.splice(i, 1)
  else opened.value.push(code)
}

async function pick(code) {
  active.value = code
  try {
    node.value = await api.syllabusNode(code)
    await loadNotes(code)
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
      // 支持 /syllabus?node=party-03-02 直达某一节（任务页「去复习」等入口用）
      const target = route.query.node
      const hit = target
        ? data.value.chapters.find((c) => c.code === target
            || c.sections.some((s) => s.code === target))
        : null
      if (hit) {
        opened.value = [hit.code]
        await pick(target)
      } else {
        if (target) ElMessage.warning(`没有找到「${target}」这一节，已回到目录`)
        opened.value = [data.value.chapters[0].code]
        // 有正文就先展示本章正文，否则落到第一节
        const first = data.value.chapters[0]
        await pick(first.chars ? first.code : (first.sections[0]?.code || first.code))
      }
      // /syllabus?node=xx&hl=原文片段：AI 词条卡「原文节选」点击跳转，定位并临时高亮
      const hlq = String(route.query.hl || '').replace(/\+/g, ' ').trim()
      if (hlq) {
        // pick() 里给 node 赋值触发的 watch（会清 flash）是异步 flush 的，
        // 不等它跑完就设 flash 会被它清掉 —— 先 nextTick 让“清”发生完再“设”
        await nextTick()
        locateQuote(hlq)
      }
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})

// 页面已打开时 AI 浮窗再次联动跳转（route.query 变化）也要能定位
watch(() => [route.query.node, route.query.hl], async ([n, hl]) => {
  if (!n) return
  if (n !== active.value) {
    const hit = data.value.chapters.find((c) => c.code === n || c.sections.some((s) => s.code === n))
    if (!hit) return
    opened.value = [hit.code]
    await pick(n)
  }
  if (hl) {
    await nextTick() // 同上：等 watch(node) 的 flash 清空先落地
    locateQuote(String(hl).replace(/\+/g, ' '))
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
.text-dot { width: 5px; height: 5px; border-radius: 50%; background: #67c23a; flex: none; }
.text-dot.sm { width: 4px; height: 4px; background: #c0e0a8; margin-right: 2px; }
.sections { padding-bottom: 6px; }
.section { display: flex; align-items: center; gap: 8px; padding: 7px 14px 7px 30px; cursor: pointer; font-size: 12px; color: #606266; line-height: 1.5; }
.section:hover { background: #f5f7fa; }
.section.active { background: #ecf5ff; color: #409eff; }
.section.chapter-text { color: #909399; font-size: 11px; }
.sec-chars { font-size: 10px; color: #c0c4cc; }
.sec-title { flex: 1; }
.sec-stat { color: #409eff; }
.node-path { font-size: 15px; font-weight: 600; color: #303133; line-height: 1.6; }
.node-meta { display: flex; align-items: center; gap: 10px; margin: 8px 0 18px; }
.text-block { background: #fcfcfd; border: 1px solid #f0f2f5; border-radius: 8px; padding: 4px 16px 14px; }
.text-head { margin-top: 10px; }
.text-count { font-size: 11px; color: #c0c4cc; font-style: normal; margin-left: 6px; }
.text-tools { display: flex; align-items: center; gap: 2px; }
.text-body { font-size: 15px; line-height: 1.95; color: #303133; letter-spacing: .2px; max-height: 62vh; overflow-y: auto; padding-right: 6px; }
.text-body p { margin: 0 0 1em; text-indent: 2em; text-align: justify; }
.text-body mark { all: unset; }
.mk { border-radius: 3px; padding: 1px 0; cursor: pointer; }
.mk.c-yellow { background: #ffe58f; }
.mk.c-purple { background: #d3adf7; }
.mk.c-green { background: #b7eb8f; }
.mk.c-blue { background: #91caff; }
.mk.c-pink { background: #ffadd2; }
.mk.c-flash { background: #ffc9c9; outline: 2px solid #ff7875; border-radius: 4px; }
.text-hint { font-size: 11px; color: #c0c4cc; text-align: right; padding-top: 4px; }
.note-count { color: #e6a23c; }
.sel-bar {
  position: fixed; z-index: 3000; display: flex; align-items: center; gap: 8px;
  background: #303133; border-radius: 8px; padding: 6px 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .25);
}
.sel-dot { width: 16px; height: 16px; border-radius: 50%; cursor: pointer; border: 1px solid rgba(255, 255, 255, .35); flex: none; }
.sel-dot.big { width: 20px; height: 20px; border: 2px solid transparent; }
.sel-dot.big.on { border-color: #409eff; }
.sel-btn { color: #fff; font-size: 12px; cursor: pointer; padding: 0 2px; }
.sel-btn:hover { color: #79bbff; }
.note-quote {
  background: #fafafa; border-left: 3px solid #ffe58f; padding: 8px 10px;
  font-size: 13px; color: #606266; line-height: 1.7; margin-bottom: 10px;
  max-height: 120px; overflow-y: auto;
}
.color-row { display: flex; gap: 10px; margin-top: 10px; align-items: center; }
.text-missing { font-size: 12px; color: #909399; line-height: 1.8; padding: 6px 0 2px; }
.block-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #606266; margin: 16px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #f0f2f5; }
.kp-item { padding: 8px 0; border-bottom: 1px dashed #f0f2f5; }
.kp-title { font-size: 13px; color: #303133; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.kp-desc { font-size: 12px; margin-top: 4px; line-height: 1.6; }
.event-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 6px 0; font-size: 13px; color: #303133; }
.event-year { color: #409eff; font-variant-numeric: tabular-nums; min-width: 52px; }
.event-digest { flex-basis: 100%; font-size: 12px; padding-left: 60px; }
</style>
