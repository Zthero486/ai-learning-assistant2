<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in totalCards" :key="card.label">
        <el-card class="page-card stat-card" @click="$router.push(card.to)">
          <div class="muted">{{ card.label }} <span class="arrow">›</span></div>
          <div class="num">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card class="page-card">
          <template #header>史实要点掌握情况（正确率）</template>
          <el-empty v-if="!perKp.length" description="先导入史料、建立要点并完成自测，这里会出现统计" />
          <div v-for="k in perKp" :key="k.kp_id" class="kp-row">
            <span class="kp-title">{{ k.title }}</span>
            <el-tag v-if="k.weak" type="danger" size="small" style="margin-right:8px">薄弱</el-tag>
            <el-progress
              style="flex:1"
              :percentage="k.accuracy ?? 0"
              :status="k.weak ? 'exception' : (k.accuracy >= 80 ? 'success' : undefined)"
            />
            <span class="muted">{{ k.attempts }} 次</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card class="page-card stat-card" @click="$router.push('/tasks')">
          <template #header>近 3 天待复习 <span class="header-arrow">去处理 ›</span></template>
          <el-empty v-if="!dueTasks.length" description="暂无近期到期任务" :image-size="60" />
          <div v-for="t in dueTasks" :key="t.id" class="due-row">
            <el-tag type="warning" size="small">{{ t.due_date }}</el-tag>
            <span style="margin-left:8px">{{ t.title }}</span>
          </div>
        </el-card>
        <el-card class="page-card stat-card" @click="$router.push('/ai')">
          <template #header>AI 引擎状态 <span class="header-arrow">去配置 ›</span></template>
          <el-result
            v-if="aiAvailable !== null"
            :icon="aiAvailable ? 'success' : 'info'"
            :title="aiAvailable ? '大模型 API 已就绪' : '未配置 API Key（规则引擎模式）'"
            :sub-title="aiSubTitle"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const stats = ref({ totals: {}, per_kp: [] })
const dueTasks = ref([])
const aiAvailable = ref(null)
const aiSource = ref('none')
const aiModel = ref('')

const aiSubTitle = computed(() => {
  if (!aiAvailable.value) {
    return '功能可用但为检索式降级；到「AI 助手 → 配置 API Key」选平台、粘贴 Key 即可启用大模型（免改文件）'
  }
  const who = aiSource.value === 'builtin' ? '内置阶跃 StepFun（默认）' : '自建大模型'
  const model = aiModel.value ? `（${aiModel.value}）` : ''
  return `${who}${model} —— 答疑 / 总结 / 出题均由大模型驱动`
})

const totalCards = computed(() => [
  { label: '史料笔记', value: stats.value.totals.materials ?? 0, to: '/materials' },
  { label: '史实要点', value: stats.value.totals.kps ?? 0, to: '/knowledge' },
  { label: '自测次数', value: stats.value.totals.attempts ?? 0, to: '/practice' },
  { label: '未解决错题', value: stats.value.totals.unresolved_wrong ?? 0, to: '/wrong-book' },
])

const perKp = computed(() => stats.value.per_kp)

onMounted(async () => {
  try {
    stats.value = await api.statsOverview()
    dueTasks.value = await api.dueSoon(3)
    const h = await api.aiHealth()
    aiAvailable.value = h.ai_available
    aiSource.value = h.ai_source || 'none'
    aiModel.value = h.ai_model || ''
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.num { font-size: 28px; font-weight: 700; margin-top: 6px; }
.stat-card { cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(64, 158, 255, 0.18); }
.stat-card:hover .arrow { opacity: 1; }
.arrow { float: right; color: #409eff; opacity: 0; transition: opacity 0.15s; }
.header-arrow { float: right; font-size: 12px; font-weight: 400; color: #409eff; opacity: 0; transition: opacity 0.15s; }
.stat-card:hover .header-arrow { opacity: 1; }
.kp-row { display: flex; align-items: center; margin: 10px 0; gap: 4px; }
.kp-title { width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.due-row { margin: 8px 0; }
</style>
