<template>
  <div class="nav">
    <div class="logo">
      <span class="logo-text">📜 四史学习助手</span>
      <span class="track-chip" v-if="trackName" :style="{ borderColor: trackColor, color: trackColor }">
        {{ trackName }}
      </span>
    </div>
    <el-menu :default-active="$route.path" router @select="onSelect">
      <el-menu-item index="/"><el-icon><Odometer /></el-icon>学习看板</el-menu-item>
      <el-menu-item index="/syllabus"><el-icon><Notebook /></el-icon>教材目录</el-menu-item>
      <el-menu-item index="/timeline"><el-icon><Clock /></el-icon>四史时间轴</el-menu-item>
      <el-menu-item index="/materials"><el-icon><FolderOpened /></el-icon>史料笔记</el-menu-item>
      <el-menu-item index="/knowledge"><el-icon><Collection /></el-icon>史实要点</el-menu-item>
      <el-menu-item index="/tasks"><el-icon><List /></el-icon>复习任务</el-menu-item>
      <el-menu-item index="/practice"><el-icon><EditPen /></el-icon>自测</el-menu-item>
      <el-menu-item index="/wrong-book"><el-icon><WarningFilled /></el-icon>错题本</el-menu-item>
      <el-menu-item index="/ai"><el-icon><ChatDotRound /></el-icon>AI 对话</el-menu-item>
    </el-menu>
    <div class="user-box">
      <div class="search-hint" @click="openSearch">🔍 搜索 <span class="kbd">Ctrl+K</span></div>
      <div class="phone-hint" @click="openPhone">📱 手机访问（扫码）</div>
      <div class="user-name">👤 {{ username }}</div>
      <div class="mini-links">
        <router-link to="/ai-tools" class="mini-link">AI 工具台</router-link>
        <router-link to="/welcome" class="mini-link">切换课程</router-link>
        <router-link to="/sync" class="mini-link">数据同步</router-link>
        <el-button size="small" type="danger" plain @click="$emit('logout')">退出</el-button>
      </div>
    </div>

    <el-dialog v-model="phoneVisible" title="在手机 / 平板上学习" width="380px" align-center>
      <div class="phone-box">
        <canvas ref="qrEl" class="qr"></canvas>
        <div class="phone-url">
          <el-select v-if="lanUrls.length > 1" v-model="selectedUrl" style="width: 100%" @change="renderQr">
            <el-option v-for="u in lanUrls" :key="u" :value="u" :label="u" />
          </el-select>
          <span v-else class="muted">{{ selectedUrl }}</span>
        </div>
        <ol class="phone-steps">
          <li>手机和电脑连**同一个 WiFi**</li>
          <li>用手机相机/微信扫上方二维码（或手动输入地址）</li>
          <li>登录后点浏览器菜单「添加到主屏幕」，就像装了个 App</li>
        </ol>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="打不开？两件事检查"
          description="① 启动程序时要用「手机访问」模式（命令行运行 exe 加 --lan，或设置环境变量 APP_HOST=0.0.0.0）；② 首次启动 Windows 防火墙弹窗时勾选「专用网络」允许。"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
// 侧栏导航抽成组件：桌面固定左侧，手机塞进抽屉，一套 DOM 两处复用
import { ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import QRCode from 'qrcode'
import {
  Odometer, FolderOpened, Collection, List, EditPen, WarningFilled, ChatDotRound, Clock, Notebook,
} from '@element-plus/icons-vue'
import { auth } from '../api'
import api from '../api'

const emit = defineEmits(['navigate', 'logout', 'search'])
const route = useRoute()

// ---------- 手机访问 ----------
const phoneVisible = ref(false)
const qrEl = ref(null)
const lanUrls = ref([])
const selectedUrl = ref('')
const isLocalHost = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)

function openPhone() {
  phoneVisible.value = true
  if (!isLocalHost) {
    // 公网/局域网 IP 直接访问的场景：当前地址本身就能在手机上打开
    lanUrls.value = []
    selectedUrl.value = window.location.origin
  }
}

watch(phoneVisible, async (v) => {
  if (!v) return
  if (isLocalHost && !lanUrls.value.length) {
    try {
      const r = await api.lan()
      const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80')
      lanUrls.value = (r.ips || []).map((ip) => `http://${ip}:${port}`)
    } catch { /* 拿不到就只显示当前地址 */ }
    if (!selectedUrl.value) selectedUrl.value = lanUrls.value[0] || window.location.origin
  }
  nextTick(renderQr)
})

function renderQr() {
  if (!qrEl.value || !selectedUrl.value) return
  QRCode.toCanvas(qrEl.value, selectedUrl.value, { width: 220, margin: 1 }, () => {})
}

const TRACKS = {
  party: { name: '党史', color: '#c0392b' },
  prc: { name: '新中国史', color: '#c47f17' },
  reform: { name: '改革开放史', color: '#1d7a4f' },
  socialism: { name: '社会主义发展史', color: '#3b5b9a' },
}

const username = ref(auth.username() || '未登录')
const trackName = ref('')
const trackColor = ref('#909399')

watch(
  () => route.fullPath,
  () => {
    username.value = auth.username() || '未登录'
    const t = TRACKS[auth.track()]
    trackName.value = t?.name || ''
    trackColor.value = t?.color || '#909399'
  },
  { immediate: true },
)

function onSelect() {
  emit('navigate')
}
function openSearch() {
  emit('search')
  emit('navigate')
}
</script>

<style scoped>
.nav { display: flex; flex-direction: column; height: 100%; background: #fff; }
.logo { padding: 16px 16px 10px; }
.logo-text { display: block; font-weight: 700; font-size: 16px; color: #409eff; }
.track-chip {
  display: inline-block; margin-top: 8px; font-size: 11px;
  border: 1px solid; border-radius: 10px; padding: 1px 8px;
}
.nav .el-menu { flex: 1; border-right: none; }
.user-box { padding: 12px 16px; border-top: 1px solid #e4e7ed; }
.search-hint {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; color: #606266; cursor: pointer;
  padding: 6px 8px; margin: 0 -8px 6px; border-radius: 6px;
}
.search-hint:hover { background: #f0f6ff; }
.kbd { font-size: 11px; color: #909399; border: 1px solid #dcdfe6; border-radius: 4px; padding: 1px 5px; }
.user-name { font-size: 13px; color: #606266; margin-bottom: 8px; }
.mini-links { display: flex; align-items: center; justify-content: space-between; gap: 4px; flex-wrap: wrap; }
.mini-link { font-size: 12px; color: #909399; text-decoration: none; }
.mini-link:hover { color: #409eff; }
.phone-hint {
  display: flex; align-items: center; font-size: 13px; color: #606266;
  cursor: pointer; padding: 6px 8px; margin: 0 -8px 6px; border-radius: 6px;
}
.phone-hint:hover { background: #f0f6ff; }
.phone-box { text-align: center; }
.qr { display: block; margin: 0 auto 10px; }
.phone-url { margin-bottom: 10px; word-break: break-all; }
.phone-steps { text-align: left; font-size: 13px; color: #606266; line-height: 1.9; padding-left: 20px; margin: 0 0 12px; }
</style>
