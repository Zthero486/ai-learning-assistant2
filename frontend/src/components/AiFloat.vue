<template>
  <!-- 浮动 AI 入口：每个页面右下角都能呼出，AI 贯穿全软件 -->
  <div>
    <button v-if="!open" class="ai-fab" title="AI 学习管家（可拖动面板）" @click="open = true">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
        <path
          d="M12 3l1.7 4.6L18 9.3l-4.3 1.7L12 15.6l-1.7-4.6L6 9.3l4.3-1.7L12 3z"
          fill="#fff"
        />
        <circle cx="19" cy="5" r="1.6" fill="#fff" opacity=".85" />
        <circle cx="5.5" cy="18.5" r="1.3" fill="#fff" opacity=".65" />
      </svg>
      <span class="fab-badge">AI</span>
    </button>

    <div
      v-else
      class="ai-float"
      :class="{ 'mobile-full': isMobile, dragged: pos }"
      :style="pos ? { left: pos.x + 'px', top: pos.y + 'px' } : null"
    >
      <div
        class="float-head"
        @pointerdown.prevent="dragStart"
        @pointermove="dragMove"
        @pointerup="dragEnd"
        @pointercancel="dragEnd"
      >
        <span class="float-title">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
            <path d="M12 3l1.7 4.6L18 9.3l-4.3 1.7L12 15.6l-1.7-4.6L6 9.3l4.3-1.7L12 3z" fill="#409eff" />
          </svg>
          AI 学习管家
        </span>
        <span class="float-hint">{{ isMobile ? '' : '按住标题栏拖动' }}</span>
        <button class="float-close" title="收起（内容会保留）" @click="open = false">✕</button>
      </div>
      <div class="float-body">
        <AiChat />
      </div>
    </div>
  </div>
</template>

<script setup>
// 每个功能页都有 AI：桌面是可拖动浮窗，手机是全屏层。
// 面板里就是完整的 AI 对话组件（/ai 页面同一份，历史记录走 localStorage 共享）。
import { ref, onMounted, onUnmounted } from 'vue'
import AiChat from '../views/AiChat.vue'

const open = ref(false)
const pos = ref(null) // null = 默认停靠右下角；拖过后用 left/top
const isMobile = ref(false)
let mql = null

let drag = null
function dragStart(e) {
  if (isMobile.value) return // 手机全屏，不拖
  const el = e.currentTarget.closest('.ai-float')
  const rect = el.getBoundingClientRect()
  drag = { dx: e.clientX - rect.left, dy: e.clientY - rect.top, w: rect.width, h: rect.height }
  pos.value = pos.value || { x: rect.left, y: rect.top }
}
function dragMove(e) {
  if (!drag) return
  const x = Math.min(Math.max(e.clientX - drag.dx, 4), window.innerWidth - drag.w - 4)
  const y = Math.min(Math.max(e.clientY - drag.dy, 4), window.innerHeight - 56)
  pos.value = { x: Math.round(x), y: Math.round(y) }
}
function dragEnd() {
  drag = null
}

function syncMobile(e) {
  isMobile.value = e.matches
}
onMounted(() => {
  mql = window.matchMedia('(max-width: 768px)')
  isMobile.value = mql.matches
  mql.addEventListener('change', syncMobile)
})
onUnmounted(() => mql?.removeEventListener('change', syncMobile))
</script>

<style scoped>
.ai-fab {
  position: fixed;
  right: 26px;
  bottom: 30px;
  z-index: 1400;
  width: 52px;
  height: 52px;
  border: none;
  border-radius: 50%;
  background: #409eff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 18px rgba(64, 158, 255, 0.4);
  transition: transform 0.15s;
}
.ai-fab:hover { transform: scale(1.07); }
.fab-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  background: #e24b4a;
  color: #fff;
  font-size: 10px;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 8px;
  font-weight: 500;
}

.ai-float {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1450;
  width: 440px;
  height: min(680px, calc(100vh - 90px));
  background: #fff;
  border: 0.5px solid var(--color-border-secondary, #dcdfe6);
  border-radius: 12px;
  box-shadow: 0 10px 34px rgba(0, 0, 0, 0.16);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ai-float.mobile-full {
  inset: 0 !important;
  width: auto !important;
  height: auto !important;
  border-radius: 0;
  border: none;
  right: auto;
  bottom: auto;
}
.float-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 10px;
  background: #f5f9ff;
  border-bottom: 1px solid #ebeef5;
  cursor: grab;
  user-select: none;
  flex: 0 0 auto;
}
.ai-float.mobile-full .float-head { cursor: default; }
.float-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; color: #34405c; }
.float-hint { flex: 1; font-size: 11px; color: #b1b7c2; }
.float-close {
  border: none;
  background: transparent;
  color: #909399;
  font-size: 15px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}
.float-close:hover { background: #ebeef5; color: #34405c; }
.float-body { flex: 1; min-height: 0; position: relative; }

/* 关键：把完整对话页塞进浮窗 —— 盖掉它自带的外框和视口高度 */
.float-body :deep(.chat-wrap) {
  height: 100% !important;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
</style>
