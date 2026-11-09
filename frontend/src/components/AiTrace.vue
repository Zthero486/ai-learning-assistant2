<template>
  <div v-if="trace && trace.length" :class="['ai-trace', { compact }]">
    <div class="at-head" @click="open = !open">
      <span class="at-dot" :class="{ run: pending }"></span>
      <span class="at-title">执行轨迹</span>
      <span class="at-meta">{{ metaText }}</span>
      <span class="at-toggle">{{ open ? '收起' : '展开' }}</span>
    </div>

    <div v-show="open" class="at-body">
      <div
        v-for="(t, i) in trace"
        :key="i"
        :class="['at-item', 'k-' + t.kind, { fail: t.ok === false, running: t.ok === null && t.kind === 'tool' }]"
      >
        <template v-if="t.kind === 'state'">
          <span class="at-ico">{{ stateIcon(t.state) }}</span>
          <span class="at-txt">{{ stateText(t) }}</span>
        </template>

        <template v-else-if="t.kind === 'reflow'">
          <span class="at-ico">↻</span>
          <span class="at-txt">
            <b>审查未通过，回流继续</b>
            <em class="at-gap">{{ t.reason }}</em>
          </span>
        </template>

        <template v-else-if="t.kind === 'think'">
          <span class="at-ico">🧠</span>
          <span class="at-txt at-think">{{ t.text }}</span>
        </template>

        <template v-else>
          <span class="at-ico">{{ t.ok === false ? '✕' : (t.ok === null ? '…' : '✓') }}</span>
          <span class="at-txt">
            <span class="at-tool">{{ toolLabel(t.tool) }}</span>
            <span class="at-badge" :class="t.write ? 'w' : 'r'">{{ t.write ? '写' : '读' }}</span>
            <span v-if="t.argText" class="at-args">{{ t.argText }}</span>
            <span class="at-res">{{ t.summary }}</span>
            <span v-if="t.ms != null" class="at-ms">{{ t.ms }}ms</span>
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toolLabel } from '../composables/useAiConversation'

const props = defineProps({
  trace: { type: Array, default: () => [] },
  pending: { type: Boolean, default: false },
  elapsedMs: { type: Number, default: 0 },
  startAt: { type: Number, default: 0 },
  compact: { type: Boolean, default: false },
})

const open = ref(props.pending || !props.compact)
const now = ref(Date.now())
let timer = null

watch(
  () => props.pending,
  (v) => {
    if (v) {
      open.value = true
      if (!timer) timer = setInterval(() => { now.value = Date.now() }, 500)
    } else {
      if (timer) { clearInterval(timer); timer = null }
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const ticks = computed(() => props.trace.filter((t) => t.kind === 'tool').length)
const rounds = computed(() => {
  const rs = props.trace.map((t) => t.round).filter(Boolean)
  return rs.length ? Math.max(...rs) : 0
})
const spentMs = computed(() => {
  if (props.pending && props.startAt) return now.value - props.startAt
  return props.elapsedMs || 0
})
const metaText = computed(() => {
  const sec = (spentMs.value / 1000).toFixed(spentMs.value < 10000 ? 1 : 0)
  const tail = `${rounds.value} 轮 · ${ticks.value} 次调用 · ${sec}s`
  return props.pending ? `运行中 · ${tail}` : `已完成 · ${tail}`
})

function stateIcon(s) {
  return { act: '▶', review: '🔍', finalize: '■' }[s] || '·'
}
function stateText(t) {
  if (t.state === 'act') return `开始执行（第 ${t.round || 1} 轮）`
  if (t.state === 'review') return `质量自查：这一步的结果能满足要求吗？`
  if (t.state === 'finalize') return '收尾，整理答复'
  return t.state
}
</script>

<style scoped>
.ai-trace {
  margin: 0 0 8px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fbfcfe;
  overflow: hidden;
  font-size: 12px;
}
.at-head {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; cursor: pointer; user-select: none;
  background: #f5f7fa; color: #606266;
}
.at-dot { width: 7px; height: 7px; border-radius: 50%; background: #c0c4cc; flex: none; }
.at-dot.run { background: #409eff; box-shadow: 0 0 0 0 rgba(64, 158, 255, .6); animation: at-pulse 1.2s infinite; }
@keyframes at-pulse {
  0% { box-shadow: 0 0 0 0 rgba(64, 158, 255, .5); }
  70% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0); }
}
.at-title { font-weight: 600; color: #303133; }
.at-meta { color: #909399; flex: 1; }
.at-toggle { color: #409eff; flex: none; }
.at-body { padding: 6px 10px 8px; display: flex; flex-direction: column; gap: 5px; }
.at-item { display: flex; gap: 6px; line-height: 1.6; color: #606266; }
.at-ico { width: 14px; flex: none; text-align: center; color: #909399; font-size: 11px; }
.at-item.k-state .at-txt { color: #909399; }
.at-item.k-reflow { color: #e6a23c; }
.at-item.k-think .at-think { color: #7a5af8; font-style: italic; }
.at-item.running .at-ico { color: #409eff; }
.at-item.fail { color: #f56c6c; }
.at-tool { color: #303133; font-weight: 500; }
.at-badge {
  display: inline-block; margin: 0 4px; padding: 0 4px; border-radius: 3px;
  font-size: 10px; line-height: 15px; vertical-align: 1px;
}
.at-badge.w { background: #fdf6ec; color: #e6a23c; }
.at-badge.r { background: #f4f4f5; color: #909399; }
.at-args {
  color: #909399; font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 11px; margin-right: 6px;
}
.at-res { color: #606266; }
.at-item.fail .at-res { color: #f56c6c; }
.at-ms { color: #c0c4cc; margin-left: 6px; font-size: 10px; }
.at-gap { color: #e6a23c; font-style: normal; display: block; font-size: 11px; }
.compact .at-body { max-height: 180px; overflow-y: auto; }
</style>
