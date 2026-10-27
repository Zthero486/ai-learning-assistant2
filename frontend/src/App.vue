<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">📘 AI 学习助手</div>
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/"><el-icon><Odometer /></el-icon>学习看板</el-menu-item>
        <el-menu-item index="/materials"><el-icon><FolderOpened /></el-icon>课程资料</el-menu-item>
        <el-menu-item index="/knowledge"><el-icon><Collection /></el-icon>知识点</el-menu-item>
        <el-menu-item index="/tasks"><el-icon><List /></el-icon>学习任务</el-menu-item>
        <el-menu-item index="/practice"><el-icon><EditPen /></el-icon>练习</el-menu-item>
        <el-menu-item index="/wrong-book"><el-icon><WarningFilled /></el-icon>错题本</el-menu-item>
        <el-menu-item index="/ai"><el-icon><ChatDotRound /></el-icon>AI 助手</el-menu-item>
      </el-menu>
      <div class="user-box">
        <div class="user-name">👤 {{ username }}</div>
        <el-button size="small" type="danger" plain @click="logout">退出登录</el-button>
      </div>
    </el-aside>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
// v1.1：侧栏底部加当前用户与退出
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Odometer, FolderOpened, Collection, List, EditPen, WarningFilled, ChatDotRound } from '@element-plus/icons-vue'
import { auth } from './api'

const router = useRouter()
const username = computed(() => auth.username() || '未登录')

function logout() {
  auth.clear()
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
.user-name { font-size: 13px; color: #606266; margin-bottom: 8px; }
.main { overflow: auto; }
.page-card { margin-bottom: 16px; }
.muted { color: #909399; font-size: 13px; }
</style>
