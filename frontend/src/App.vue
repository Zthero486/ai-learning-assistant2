<template>
  <el-container class="layout">
    <!-- 桌面：固定左侧栏 -->
    <el-aside v-if="!isMobile" width="200px" class="aside">
      <SideNav ref="navRef" @logout="logout" @search="openSearch" />
    </el-aside>

    <!-- 手机/窄屏：抽屉 + 顶栏 -->
    <el-drawer v-if="isMobile" v-model="drawer" direction="ltr" size="230px" :with-header="false">
      <SideNav @navigate="drawer = false" @logout="logout" @search="openSearch" />
    </el-drawer>

    <el-container class="right">
      <div v-if="isMobile" class="mobile-bar">
        <el-button text class="burger" @click="drawer = true">
          <el-icon :size="20"><Fold /></el-icon>
        </el-button>
        <span class="m-title">四史学习助手</span>
        <span
          v-if="trackName"
          class="track-chip"
          :style="{ borderColor: trackColor, color: trackColor }"
        >{{ trackName }}</span>
      </div>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <GlobalSearch ref="gs" />
  </el-container>
</template>

<script setup>
// v1.2：侧栏底部加搜索入口、当前用户与退出
// v2.0：四史改造——侧栏显示当前选中的那一门课
// v2.1：手机/平板适配——窄屏隐藏侧栏，改抽屉 + 顶栏
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Fold } from '@element-plus/icons-vue'
import { auth } from './api'
import SideNav from './components/SideNav.vue'
import GlobalSearch from './components/GlobalSearch.vue'

const TRACKS = {
  party: { name: '党史', color: '#c0392b' },
  prc: { name: '新中国史', color: '#c47f17' },
  reform: { name: '改革开放史', color: '#1d7a4f' },
  socialism: { name: '社会主义发展史', color: '#3b5b9a' },
}

const MOBILE_QUERY = '(max-width: 768px)'
const router = useRouter()
const route = useRoute()
const gs = ref(null)
const navRef = ref(null)
const drawer = ref(false)
const isMobile = ref(false)

let mql = null
function syncMobile(e) {
  isMobile.value = e.matches
  if (!e.matches) drawer.value = false
}

const trackName = ref('')
const trackColor = ref('#909399')

watch(
  () => route.fullPath,
  () => {
    const t = TRACKS[auth.track()]
    trackName.value = t?.name || ''
    trackColor.value = t?.color || '#909399'
  },
  { immediate: true },
)

function logout() {
  auth.clear()
  drawer.value = false
  router.push('/login')
}
function openSearch() {
  // 抽屉打开时先关抽屉，再delay一点让动画走完再弹搜索框
  setTimeout(() => gs.value?.open(), isMobile.value ? 260 : 0)
}

onMounted(() => {
  mql = window.matchMedia(MOBILE_QUERY)
  isMobile.value = mql.matches
  mql.addEventListener('change', syncMobile)
})
onUnmounted(() => mql?.removeEventListener('change', syncMobile))
</script>

<style>
body { margin: 0; background: #f5f7fa; -webkit-text-size-adjust: 100%; }
.layout { height: 100vh; height: 100dvh; }
.aside { background: #fff; border-right: 1px solid #e4e7ed; display: flex; flex-direction: column; }
.aside .el-menu { flex: 1; }
.right { flex-direction: column; min-width: 0; }
.main { overflow: auto; -webkit-overflow-scrolling: touch; }
.page-card { margin-bottom: 16px; }
.muted { color: #909399; font-size: 13px; }

.mobile-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 48px;
  padding: 0 8px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex: 0 0 auto;
}
.mobile-bar .burger { padding: 6px; }
.m-title { font-weight: 700; font-size: 15px; color: #409eff; flex: 1; }
.mobile-bar .track-chip { font-size: 11px; border: 1px solid; border-radius: 10px; padding: 1px 8px; }

/* 窄屏通用收紧：卡片留白、弹窗宽度、表格字号 —— 不改各页面单独写的一份 CSS */
@media (max-width: 768px) {
  .el-main { padding: 10px !important; }
  .el-card__header { padding: 10px 12px; font-size: 14px; }
  .el-card__body { padding: 12px; }
  .page-card { margin-bottom: 10px; }
  .el-dialog { width: 92% !important; margin-top: 6vh !important; }
  .el-message-box { width: 88% !important; }
  .el-table { font-size: 12.5px; }
  .el-table .cell { padding: 0 6px; }
  .el-form-item { margin-bottom: 12px; }
  .el-form-item__label { font-size: 13px; }
  .el-button + .el-button { margin-left: 6px; }
  .el-tag { font-size: 11px; }
  .el-row { row-gap: 0; }
  /* 表格横向滑动时给个提示，避免以为内容被裁掉了 */
  .el-table__body-wrapper, .el-scrollbar__wrap { -webkit-overflow-scrolling: touch; }
}
</style>
