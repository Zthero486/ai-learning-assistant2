<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in totalCards" :key="card.label">
        <el-card class="page-card">
          <div class="muted">{{ card.label }}</div>
          <div class="num">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card class="page-card">
          <template #header>知识点掌握情况（正确率）</template>
          <el-empty v-if="!perKp.length" description="先导入资料并创建知识点、完成练习后这里会出现统计" />
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
        <el-card class="page-card">
          <template #header>近 3 天到期任务</template>
          <el-empty v-if="!dueTasks.length" description="暂无近期到期任务" :image-size="60" />
          <div v-for="t in dueTasks" :key="t.id" class="due-row">
            <el-tag type="warning" size="small">{{ t.due_date }}</el-tag>
            <span style="margin-left:8px">{{ t.title }}</span>
          </div>
        </el-card>
        <el-card class="page-card">
          <template #header>AI 引擎状态</template>
          <el-result
            v-if="aiAvailable !== null"
            :icon="aiAvailable ? 'success' : 'info'"
            :title="aiAvailable ? 'DeepSeek API 已连接' : '未配置 API Key（规则引擎模式）'"
            :sub-title="aiAvailable ? '答疑/总结/出题均由大模型驱动' : '功能可用但为检索式降级；在 backend/.env 配置 DEEPSEEK_API_KEY 后启用大模型'"
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

const totalCards = computed(() => [
  { label: '课程资料', value: stats.value.totals.materials ?? 0 },
  { label: '知识点', value: stats.value.totals.kps ?? 0 },
  { label: '练习次数', value: stats.value.totals.attempts ?? 0 },
  { label: '未解决错题', value: stats.value.totals.unresolved_wrong ?? 0 },
])

const perKp = computed(() => stats.value.per_kp)

onMounted(async () => {
  try {
    stats.value = await api.statsOverview()
    dueTasks.value = await api.dueSoon(3)
    aiAvailable.value = (await api.aiHealth()).ai_available
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.num { font-size: 28px; font-weight: 700; margin-top: 6px; }
.kp-row { display: flex; align-items: center; margin: 10px 0; gap: 4px; }
.kp-title { width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.due-row { margin: 8px 0; }
</style>
