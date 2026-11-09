// v1.1 API 封装：fetch + JSON + Bearer 令牌 + 统一错误提示
const TOKEN_KEY = 'lp_token'
const USER_KEY = 'lp_user'

export const auth = {
  token: () => localStorage.getItem(TOKEN_KEY) || '',
  username: () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null')?.username || '' } catch { return '' }
  },
  user: () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') } catch { return null }
  },
  // 当前选中的那一门四史（party/prc/reform/socialism），空串 = 还没选课
  track: () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null')?.track || '' } catch { return '' }
  },
  setTrack: (key) => {
    try {
      const u = JSON.parse(localStorage.getItem(USER_KEY) || 'null') || {}
      u.track = key
      localStorage.setItem(USER_KEY, JSON.stringify(u))
    } catch { /* ignore */ }
  },
  save: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
}

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const token = auth.token()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(url, { ...options, headers })
  if (!resp.ok) {
    // 令牌失效/缺失：清掉本地登录态，回登录页
    if (resp.status === 401 && !url.startsWith('/api/auth/')) {
      auth.clear()
      window.location.assign('/login')
      throw new Error('登录已过期，请重新登录')
    }
    let detail = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

// AI 对话（SSE）：POST 带 body，只能走 fetch + ReadableStream，EventSource 不支持 POST。
// 服务端事件：step/start、step/end、error、done
async function streamChat(payload, { onEvent, signal } = {}) {
  const resp = await fetch('/api/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token()}` },
    body: JSON.stringify(payload),
    signal,
  })
  if (!resp.ok) {
    if (resp.status === 401) {
      auth.clear()
      window.location.assign('/login')
      throw new Error('登录已过期，请重新登录')
    }
    let detail = `请求失败 (${resp.status})`
    try { const d = await resp.json(); if (d.detail) detail = d.detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  const ctype = resp.headers.get('content-type') || ''
  // 未配置 key 时后端直接回 JSON，这里兜住，别让界面卡在「思考中」
  if (!ctype.includes('text/event-stream')) {
    const data = await resp.json()
    onEvent?.({ type: 'done', reply: data.reply || '', steps: data.steps || [], mode: data.mode })
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let cut
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try { onEvent?.(JSON.parse(line.slice(6))) } catch { /* 半包/心跳，忽略 */ }
      }
    }
  }
}

// 带 Authorization 的文件下载（浏览器 <a> 下载带不了请求头，所以走 fetch+blob）
async function downloadFile(url, filename) {
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${auth.token()}` } })
  if (!resp.ok) {
    let detail = `导出失败 (${resp.status})`
    try { const d = await resp.json(); if (d.detail) detail = d.detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

export default {
  // 认证
  register: (body) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request('/api/auth/me'),
  // 四史课程
  tracks: () => request('/api/tracks'),
  setTrack: (track) => request('/api/profile/track', { method: 'POST', body: JSON.stringify({ track }) }),
  syllabus: (track) => request(`/api/syllabus${track ? `?track=${encodeURIComponent(track)}` : ''}`),
  syllabusNode: (code) => request(`/api/syllabus/node/${encodeURIComponent(code)}`),
  // 资料
  listMaterials: (course) => request(`/api/materials${course ? `?course=${encodeURIComponent(course)}` : ''}`),
  getMaterial: (id) => request(`/api/materials/${id}`),
  uploadMaterial: (file, course, filename) => {
    const fd = new FormData()
    // 传 Blob 快照时必须显式给文件名，否则后端只能拿到 "blob"
    fd.append('file', file, filename || file.name || 'upload')
    fd.append('course', course)
    return request('/api/materials/upload', { method: 'POST', body: fd })
  },
  deleteMaterial: (id) => request(`/api/materials/${id}`, { method: 'DELETE' }),
  // 知识点（兼容旧的 listKps('课程名') 写法）
  listKps: (arg = {}) => {
    const opt = typeof arg === 'string' ? { course: arg } : arg
    const qs = new URLSearchParams()
    if (opt.course) qs.set('course', opt.course)
    if (opt.track) qs.set('track', opt.track)
    if (opt.nodeCode) qs.set('node_code', opt.nodeCode)
    const q = qs.toString()
    return request(`/api/knowledge-points${q ? `?${q}` : ''}`)
  },
  createKp: (body) => request('/api/knowledge-points', { method: 'POST', body: JSON.stringify(body) }),
  updateKp: (id, body) => request(`/api/knowledge-points/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteKp: (id) => request(`/api/knowledge-points/${id}`, { method: 'DELETE' }),
  // 任务
  listTasks: () => request('/api/tasks'),
  createTask: (body) => request('/api/tasks', { method: 'POST', body: JSON.stringify(body) }),
  setTaskStatus: (id, status) => request(`/api/tasks/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
  dueSoon: (days = 3) => request(`/api/tasks/due-soon?days=${days}`),
  // 练习与错题
  generateQuestions: (body) => request('/api/questions/generate', { method: 'POST', body: JSON.stringify(body) }),
  listQuestions: (kpId) => request(`/api/questions${kpId ? `?kp_id=${kpId}` : ''}`),
  submitPractice: (body) => request('/api/practice/submit', { method: 'POST', body: JSON.stringify(body) }),
  practiceSummary: () => request('/api/practice/summary'),
  // 语音转文字：录音 Blob 上传，服务端转发到 OpenAI 兼容 ASR（.env 里 AI_ASR_URL）
  transcribe: (blob) => {
    const fd = new FormData()
    fd.append('file', blob, 'voice.webm')
    return request('/api/ai/transcribe', { method: 'POST', body: fd })
  },
  wrongBook: (onlyUnresolved = true) => request(`/api/wrong-book?only_unresolved=${onlyUnresolved}`),
  // 今日复习队列（FSRS 排期到期的错题）
  reviewDue: (limit = 20) => request(`/api/review/due?limit=${limit}`),
  updateWrong: (id, body) => request(`/api/wrong-book/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  // 直接跳转下载：Content-Disposition 的真文件名在平板等移动端下载管理器里才生效
  // （fetch+blob 的 a.download 属性会被移动端忽略，落成 UUID.txt）
  exportWrongCsv: (onlyUnresolved = false) => {
    window.location.href = `/api/wrong-book/export/csv?only_unresolved=${onlyUnresolved}&token=${encodeURIComponent(auth.token())}`
    return Promise.resolve()
  },
  exportWrongPdf: (onlyUnresolved = false) => {
    window.location.href = `/api/wrong-book/export/pdf?only_unresolved=${onlyUnresolved}&token=${encodeURIComponent(auth.token())}`
    return Promise.resolve()
  },
  openWrongPrint: (onlyUnresolved = false) =>
    window.open(`/api/wrong-book/print?token=${encodeURIComponent(auth.token())}&only_unresolved=${onlyUnresolved}`, '_blank'),
  // 全局搜索
  search: (q) => request(`/api/search?q=${encodeURIComponent(q)}`),
  // 统计
  statsOverview: () => request('/api/stats/overview'),
  // 手机访问（局域网 IP 列表，用于生成扫码地址）
  lan: () => request('/api/lan'),
  // AI
  aiHealth: () => request('/api/health'),
  aiTest: () => request('/api/ai/test', { method: 'POST' }),
  aiConfig: () => request('/api/config/ai'),
  saveAiConfig: (body) => request('/api/config/ai', { method: 'POST', body: JSON.stringify(body) }),
  aiSummarize: (body) => request('/api/ai/summarize', { method: 'POST', body: JSON.stringify(body) }),
  aiAsk: (body) => request('/api/ai/ask', { method: 'POST', body: JSON.stringify(body) }),
  aiWeakAnalysis: (body) => request('/api/ai/weak-analysis', { method: 'POST', body: JSON.stringify(body) }),
  aiTools: () => request('/api/ai/tools'),
  // AI 记忆（用户画像）
  memoryList: () => request('/api/memory'),
  memoryDelete: (id) => request(`/api/memory/${id}`, { method: 'DELETE' }),
  // AI 对话窗口（Agent）：onEvent 收 SSE 事件
  aiChat: (payload, handlers) => streamChat(payload, handlers),
  // 跨机同步
  syncConfig: (body) => request('/api/sync/config', { method: 'POST', body: JSON.stringify(body) }),
  syncExport: () => request('/api/sync/export'),
  syncImport: (payload) => request('/api/sync/import', { method: 'POST', body: JSON.stringify(payload) }),
  syncPush: () => request('/api/sync/push', { method: 'POST' }),
  syncPull: () => request('/api/sync/pull', { method: 'POST' }),
  // 手动备份：下载/读取 JSON 文件（<a> 下载带不了请求头，走 fetch+blob）
  downloadSyncFile: () =>
    downloadFile('/api/sync/export', `学习数据备份-${new Date().toISOString().slice(0, 10)}.json`),
  // 历史事件与时间轴
  generatePersonal: (body) =>
    request('/api/questions/generate-personal', { method: 'POST', body: JSON.stringify(body) }),
  events: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.era) qs.set('era', params.era)
    if (params.kp_id) qs.set('kp_id', params.kp_id)
    if (params.track) qs.set('track', params.track)
    const q = qs.toString()
    return request(`/api/events${q ? `?${q}` : ''}`)
  },
  eventCreate: (body) => request('/api/events', { method: 'POST', body: JSON.stringify(body) }),
  eventUpdate: (id, body) => request(`/api/events/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  eventDelete: (id) => request(`/api/events/${id}`, { method: 'DELETE' }),
  timeline: (era = '', track = '') => {
    const qs = new URLSearchParams()
    if (era) qs.set('era', era)
    if (track) qs.set('track', track)
    const q = qs.toString()
    return request(`/api/timeline${q ? `?${q}` : ''}`)
  },
}
