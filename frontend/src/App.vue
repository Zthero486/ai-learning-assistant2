<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">📜 历史学习助手</div>
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/"><el-icon><Odometer /></el-icon>学习看板</el-menu-item>
        <el-menu-item index="/timeline"><el-icon><Clock /></el-icon>历史时间轴</el-menu-item>
        <el-menu-item index="/materials"><el-icon><FolderOpened /></el-icon>史料笔记</el-menu-item>
        <el-menu-item index="/knowledge"><el-icon><Collection /></el-icon>史实要点</el-menu-item>
        <el-menu-item index="/tasks"><el-icon><List /></el-icon>复习任务</el-menu-item>
        <el-menu-item index="/practice"><el-icon><EditPen /></el-icon>自测</el-menu-item>
        <el-menu-item index="/wrong-book"><el-icon><WarningFilled /></el-icon>错题本</el-menu-item>
        <el-menu-item index="/ai"><el-icon><ChatDotRound /></el-icon>AI 助手</el-menu-item>
      </el-menu>
      <div class="user-box">
        <div class="search-hint" @click="$refs.gs.open()">🔍 搜索 <span class="kbd">Ctrl+K</span></div>
        <div class="user-name">👤 {{ username }}</div>
        <div class="mini-links">
          <router-link to="/sync" class="mini-link">数据同步</router-link>
          <el-button size="small" type="danger" plain @click="logout">退出</el-button>
        </div>
      </div>
    </el-aside>
    <el-main class="main">
      <router-view />
    </el-main>
    <GlobalSearch ref="gs" />
  </el-container>
</template>

<script setup>
// v1.2：侧栏底部加搜索入口、当前用户与退出
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Odometer, FolderOpened, Collection, List, EditPen, WarningFilled, ChatDotRound, Clock } from '@element-plus/icons-vue'
import { auth } from './api'
import GlobalSearch from './components/GlobalSearch.vue'

const router = useRouter()
const route = useRoute()
const gs = ref(null)

// localStorage 不是响应式数据源，computed 读它永远不更新；
// 这里改为随路由跳转刷新（登录/注册/退出都会触发路由变化）
const username = ref(auth.username() || '未登录')
watch(
  () => route.fullPath,
  () => { username.value = auth.username() || '未登录' },
  { immediate: true },
)

function logout() {
  auth.clear()
  username.value = '未登录'
  router.push('/login')
}
</script>

<style>
body { margin: 0; background: #f5f7fa; }
.layout { height: 100vh; }
.aside { background: #fff; border-right: 1px solid #e4e7ed; display: flex; flex-direction: column; }
.aside .el-menu { flex: 1; }
.logo { font-weight: 700; font-size: 16px; padding: 18px 16px; color: #409eff; }
.user-box { padding: 12px 16px; border-top: 1px solid #e4e7ed; }
.search-hint { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #606266; cursor: pointer; padding: 6px 8px; margin: 0 -8px 6px; border-radius: 6px; }
.search-hint:hover { background: #f0f6ff; }
.kbd { font-size: 11px; color: #909399; border: 1px solid #dcdfe6; border-radius: 4px; padding: 1px 5px; }
.user-name { font-size: 13px; color: #606266; margin-bottom: 8px; }
.mini-links { display: flex; align-items: center; justify-content: space-between; }
.mini-link { font-size: 12px; color: #909399; text-decoration: none; }
.mini-link:hover { color: #409eff; }
.main { overflow: auto; }
.page-card { margin-bottom: 16px; }
.muted { color: #909399; font-size: 13px; }
</style>
