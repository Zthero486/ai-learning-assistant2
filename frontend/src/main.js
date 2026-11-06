import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import api from './api'

// v1.1 朴素路由：视图级组件 + 登录守卫（v2 引入 Pinia 全局状态）
import Dashboard from './views/Dashboard.vue'
import Syllabus from './views/Syllabus.vue'
import ChooseTrack from './views/ChooseTrack.vue'
import Timeline from './views/Timeline.vue'
import Materials from './views/Materials.vue'
import KnowledgePoints from './views/KnowledgePoints.vue'
import Tasks from './views/Tasks.vue'
import Practice from './views/Practice.vue'
import WrongBook from './views/WrongBook.vue'
import AiAssistant from './views/AiAssistant.vue'
import AiChat from './views/AiChat.vue'
import Sync from './views/Sync.vue'
import Login from './views/Login.vue'
import { auth } from './api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login, meta: { title: '登录', public: true } },
    // 首次登录选课页：不要求已选课，否则会自己重定向自己
    { path: '/welcome', name: 'chooseTrack', component: ChooseTrack, meta: { title: '选择课程', allowNoTrack: true } },
    { path: '/', name: 'dashboard', component: Dashboard, meta: { title: '学习看板' } },
    { path: '/syllabus', name: 'syllabus', component: Syllabus, meta: { title: '教材目录' } },
    { path: '/timeline', name: 'timeline', component: Timeline, meta: { title: '历史时间轴' } },
    { path: '/materials', name: 'materials', component: Materials, meta: { title: '史料笔记' } },
    { path: '/knowledge', name: 'knowledge', component: KnowledgePoints, meta: { title: '知识点' } },
    { path: '/tasks', name: 'tasks', component: Tasks, meta: { title: '复习任务' } },
    { path: '/practice', name: 'practice', component: Practice, meta: { title: '练习' } },
    { path: '/wrong-book', name: 'wrongBook', component: WrongBook, meta: { title: '错题本' } },
    // /ai 是主入口（对话式，AI 可直接读写数据）；/ai-tools 保留原来的答疑/总结/薄弱点工具台
    { path: '/ai', name: 'ai', component: AiChat, meta: { title: 'AI 对话' } },
    { path: '/ai-tools', name: 'aiTools', component: AiAssistant, meta: { title: 'AI 工具' } },
    { path: '/sync', name: 'sync', component: Sync, meta: { title: '数据同步' } },
  ],
})

// 未登录一律回登录页；已登录但还没选课，先去做课程选择
router.beforeEach((to) => {
  const logged = !!auth.token()
  if (to.meta.public) return logged ? { path: auth.track() ? '/' : '/welcome' } : true
  if (!logged) return { path: '/login' }
  if (!to.meta.allowNoTrack && !auth.track()) return { path: '/welcome' }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 四史学习助手` : '四史学习助手'
})

// 暴露 api 给各视图（v1 朴素做法；v2 改为模块化注入）
const app = createApp(App)
app.config.globalProperties.$api = api
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
