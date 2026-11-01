<template>
  <div class="tl-page">
    <header class="tl-head">
      <div>
        <h2>历史时间轴</h2>
        <p class="sub" v-if="counts.events">
          {{ counts.events }} 个事件 · {{ counts.eras }} 个时期 · 跨 {{ spanYears }} 年
        </p>
        <p class="sub" v-else>把笔记里的史实按时间串起来，先建第一条事件</p>
      </div>
      <div class="tools">
        <el-select v-model="eraFilter" placeholder="全部时期" clearable size="default" class="sel" @change="load">
          <el-option v-for="e in eras" :key="e.era" :label="e.era" :value="e.era" />
        </el-select>
        <el-button type="primary" @click="openCreate">新增事件</el-button>
      </div>
    </header>

    <div v-if="groups.length" class="axis">
      <section v-for="g in groups" :key="g.era" class="era">
        <div class="era-head">
          <span class="era-dot" :style="{ background: tone(g.era) }"></span>
          <span class="era-name">{{ g.era }}</span>
          <span class="era-range">{{ g.range }}</span>
          <span class="era-count">{{ g.events.length }} 件</span>
        </div>

        <ul class="events">
          <li
            v-for="e in g.events"
            :key="e.id"
            class="ev"
            :class="{ open: openId === e.id, world: g.era.includes('世界') }"
            @click="toggle(e.id)"
          >
            <span class="node" :style="{ borderColor: tone(g.era) }"></span>
            <div class="row">
              <span class="yr">{{ e.year_text }}</span>
              <span class="ttl">{{ e.title }}</span>
              <span class="ppl" v-if="e.people">{{ e.people }}</span>
            </div>

            <div v-if="openId === e.id" class="detail" @click.stop>
              <div class="kv" v-if="e.year_end_text || e.place">
                <span v-if="e.year_end_text">结束：{{ e.year_end_text }}</span>
                <span v-if="e.place">地点：{{ e.place }}</span>
              </div>
              <p v-if="e.cause"><b>背景</b>{{ e.cause }}</p>
              <p v-if="e.process"><b>经过</b>{{ e.process }}</p>
              <p v-if="e.impact"><b>影响</b>{{ e.impact }}</p>
              <p v-if="e.significance"><b>评价</b>{{ e.significance }}</p>
              <div class="tags" v-if="e.tags">
                <el-tag v-for="t in e.tags.split(',')" :key="t" size="small" effect="plain">{{ t }}</el-tag>
              </div>
              <div class="ops">
                <el-button size="small" @click="openEdit(e)">编辑</el-button>
                <el-button size="small" type="danger" plain @click="remove(e)">删除</el-button>
              </div>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <el-empty v-else description="还没有事件，点右上角新增，或运行 scripts/seed_history.py 灌入示例" />

    <el-dialog v-model="dialog" :title="form.id ? '编辑事件' : '新增事件'" width="620px">
      <el-form :model="form" label-width="72px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="如：秦统一六国" maxlength="60" />
        </el-form-item>
        <el-form-item label="时期">
          <el-input v-model="form.era" placeholder="如：战国 / 秦 / 北宋 / 世界近代" list="era-list" />
          <datalist id="era-list">
            <option v-for="e in eras" :key="e.era" :value="e.era" />
          </datalist>
        </el-form-item>
        <el-form-item label="年份">
          <div class="year-row">
            <el-input-number v-model="form.year" :controls="false" placeholder="起始年" />
            <el-input-number v-model="form.year_end" :controls="false" placeholder="结束年（可空）" />
            <span class="hint">{{ preview }}</span>
          </div>
          <div class="tip">公元前填负数，如统一六国填 -221；跨年事件再填结束年</div>
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="form.place" placeholder="如：咸阳" />
        </el-form-item>
        <el-form-item label="人物">
          <el-input v-model="form.people" placeholder="如：嬴政、李斯" />
        </el-form-item>
        <el-form-item label="背景">
          <el-input v-model="form.cause" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="经过">
          <el-input v-model="form.process" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="影响">
          <el-input v-model="form.impact" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="评价">
          <el-input v-model="form.significance" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="逗号分隔，如：统一,秦朝" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const openId = ref(null)
const eraFilter = ref('')
const events = ref([])
const eras = ref([])
const span = ref({ start: null, end: null })

const blank = () => ({
  id: null,
  title: '',
  era: '',
  year: null,
  year_end: null,
  place: '',
  people: '',
  cause: '',
  process: '',
  impact: '',
  significance: '',
  tags: '',
})
const form = reactive(blank())

const counts = computed(() => ({ events: events.value.length, eras: eras.value.length }))
const spanYears = computed(() => {
  const { start, end } = span.value
  if (start === null || end === null) return 0
  return end - start
})

// 时期配色：同名时期永远同色，不依赖后端
const PALETTE = [
  '#c0392b', '#8e6e53', '#2c6e8f', '#4f7942', '#8a5a9e',
  '#b07d2b', '#3d6b6b', '#a04545', '#5a6b8c', '#7a7a7a',
]
function tone(name) {
  if (!name) return '#909399'
  let h = 0
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 9973
  return PALETTE[h % PALETTE.length]
}

function yearText(y) {
  if (y === null || y === undefined || y === '') return ''
  return y < 0 ? `前${Math.abs(y)}年` : `${y}年`
}
const preview = computed(() => {
  if (form.year === null || form.year === undefined) return ''
  const a = yearText(form.year)
  const b = form.year_end === null || form.year_end === undefined ? '' : yearText(form.year_end)
  return b ? `${a} — ${b}` : a
})

// 按时期分组，组顺序 = 该时期最早年份；世界史单独标记，便于中外同期对照
const groups = computed(() => {
  const map = new Map()
  for (const e of events.value) {
    const key = e.era || '未分期'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(e)
  }
  return [...map.entries()]
    .map(([era, list]) => {
      const ys = list.filter((x) => x.year !== null).map((x) => x.year)
      const es = list.filter((x) => x.year_end !== null).map((x) => x.year_end)
      const start = ys.length ? Math.min(...ys) : null
      const end = ys.length ? Math.max(...ys, ...es) : null
      const range =
        start === null ? '年代待补' : end && end !== start ? `${yearText(start)}—${yearText(end)}` : yearText(start)
      return { era, events: list, start, range }
    })
    .sort((a, b) => (a.start ?? 99999) - (b.start ?? 99999))
})

async function load() {
  loading.value = true
  try {
    const data = await api.timeline(eraFilter.value || '')
    events.value = data.events
    eras.value = data.eras
    span.value = data.span || { start: null, end: null }
  } finally {
    loading.value = false
  }
}

function toggle(id) {
  openId.value = openId.value === id ? null : id
}

function openCreate() {
  Object.assign(form, blank())
  if (eraFilter.value) form.era = eraFilter.value
  dialog.value = true
}

function openEdit(e) {
  Object.assign(form, blank(), e)
  dialog.value = true
}

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('标题不能为空')
    return
  }
  saving.value = true
  try {
    const body = { ...form }
    delete body.id
    delete body.year_text
    delete body.year_end_text
    delete body.uuid
    delete body.created_at
    if (form.id) {
      await api.eventUpdate(form.id, body)
      ElMessage.success('已保存')
    } else {
      await api.eventCreate(body)
      ElMessage.success('已新增')
    }
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(e) {
  try {
    await ElMessageBox.confirm(`删除「${e.title}」？该操作不可恢复。`, '确认删除', { type: 'warning' })
  } catch {
    return
  }
  await api.eventDelete(e.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.tl-page { padding: 22px 26px 60px; max-width: 980px; }
.tl-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 22px; }
.tl-head h2 { margin: 0 0 4px; font-size: 20px; font-weight: 600; }
.sub { margin: 0; color: #8b8f96; font-size: 13px; }
.tools { display: flex; gap: 10px; align-items: center; }
.sel { width: 150px; }

.axis { position: relative; padding-left: 4px; }
.era { position: relative; margin-bottom: 6px; }
.era-head { display: flex; align-items: center; gap: 10px; padding: 14px 0 8px; }
.era-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.era-name { font-weight: 600; font-size: 15px; }
.era-range { color: #8b8f96; font-size: 12px; font-variant-numeric: tabular-nums; }
.era-count { color: #b0b3b8; font-size: 12px; margin-left: auto; }

.events { list-style: none; margin: 0; padding: 0 0 0 4px; border-left: 1px solid #e3e5e8; }
.ev { position: relative; padding: 9px 12px 9px 20px; cursor: pointer; border-radius: 8px; transition: background .15s; }
.ev:hover { background: #f7f8fa; }
.ev.open { background: #f7f8fa; }
.node { position: absolute; left: -5px; top: 15px; width: 9px; height: 9px; border-radius: 50%; background: #fff; border: 2px solid #999; box-sizing: border-box; }
.row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.yr { font-size: 12px; color: #7d8288; font-variant-numeric: tabular-nums; min-width: 68px; }
.ttl { font-size: 14px; font-weight: 500; color: #1f2329; }
.ppl { font-size: 12px; color: #b0b3b8; }

.detail { margin: 10px 0 4px 68px; padding: 12px 14px; background: #fff; border: 1px solid #e9ebee; border-radius: 8px; font-size: 13px; line-height: 1.75; color: #4a4f55; }
.detail p { margin: 0 0 6px; }
.detail b { color: #1f2329; margin-right: 8px; font-weight: 600; }
.kv { display: flex; gap: 18px; color: #8b8f96; font-size: 12px; margin-bottom: 8px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0 2px; }
.ops { margin-top: 10px; display: flex; gap: 8px; }

.year-row { display: flex; gap: 10px; align-items: center; }
.hint { color: #8b8f96; font-size: 13px; font-variant-numeric: tabular-nums; }
.tip { color: #a8adb4; font-size: 12px; line-height: 1.5; margin-top: 2px; }
:deep(.el-input-number) { width: 130px; }
</style>
