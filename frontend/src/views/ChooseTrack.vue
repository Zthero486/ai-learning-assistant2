<template>
  <div class="pick-wrap">
    <div class="head">
      <h1>你要学哪一门"四史"？</h1>
      <p class="sub">
        一个账号通常只修其中一门。选定后，教材目录、时间轴、史实要点、自测都会只围绕这一门展开。
      </p>
    </div>

    <div class="grid" v-loading="loading">
      <div
        v-for="t in tracks"
        :key="t.key"
        class="track-card"
        :class="{ active: t.key === picked }"
        :style="{ '--accent': t.color }"
        @click="picked = t.key"
      >
        <div class="bar"></div>
        <div class="card-head">
          <span class="name">{{ t.name }}</span>
          <span class="period">{{ t.period }}</span>
        </div>
        <div class="book">{{ t.book }}</div>
        <div class="meta">
          <span>{{ t.chapters }} 章</span>
          <span class="dot">·</span>
          <span>{{ t.sections }} 节</span>
        </div>
        <p class="blurb">{{ t.blurb }}</p>
        <div class="ask">主线追问：{{ t.ask }}</div>
      </div>
    </div>

    <div class="foot">
      <span class="muted" v-if="current">当前已选：{{ currentName }}（重选会切换课程，旧数据不会删除）</span>
      <span class="muted" v-else>随时可以在侧栏切换课程，已学的内容不会丢</span>
      <el-button type="primary" size="large" :disabled="!picked" :loading="saving" @click="confirm">
        {{ current ? '切换到这门课' : '开始学习' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { auth } from '../api'

const router = useRouter()
const tracks = ref([])
const picked = ref('')
const current = ref(auth.track() || '')
const loading = ref(true)
const saving = ref(false)

const currentName = computed(() => tracks.value.find((t) => t.key === current.value)?.name || '')

onMounted(async () => {
  try {
    const res = await api.tracks()
    tracks.value = res.tracks
    current.value = res.current
    picked.value = res.current || ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})

async function confirm() {
  saving.value = true
  try {
    const res = await api.setTrack(picked.value)
    auth.setTrack(res.track)
    current.value = res.track
    ElMessage.success(`已选定「${currentName.value}」`)
    router.push('/')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.pick-wrap { max-width: 980px; margin: 0 auto; padding: 40px 16px 24px; }
.head h1 { font-size: 24px; margin: 0 0 8px; color: #303133; }
.head .sub { color: #909399; font-size: 14px; margin: 0 0 28px; line-height: 1.7; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
.track-card {
  position: relative;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 18px 20px 16px 24px;
  cursor: pointer;
  transition: transform .15s, box-shadow .15s, border-color .15s;
  overflow: hidden;
}
.track-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0, 0, 0, .07); }
.track-card.active { border-color: var(--accent); box-shadow: 0 6px 18px rgba(0, 0, 0, .08); }
.bar { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--accent); opacity: .55; }
.track-card.active .bar { opacity: 1; }
.card-head { display: flex; align-items: baseline; justify-content: space-between; }
.name { font-size: 18px; font-weight: 700; color: #303133; }
.period { font-size: 12px; color: #909399; }
.book { font-size: 13px; color: #606266; margin-top: 8px; }
.meta { font-size: 12px; color: var(--accent); margin-top: 6px; }
.meta .dot { margin: 0 6px; }
.blurb { font-size: 13px; color: #909399; line-height: 1.7; margin: 10px 0 12px; }
.ask { font-size: 12px; color: #606266; background: #fafafa; border-radius: 6px; padding: 6px 10px; }
.foot { display: flex; align-items: center; justify-content: space-between; margin-top: 26px; }
.muted { color: #909399; font-size: 13px; }
</style>
