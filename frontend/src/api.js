// v1 朴素 API 封装：fetch + JSON + 统一错误提示
async function request(url, options = {}) {
  const resp = await fetch(url, {
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

export default {
  // 资料
  listMaterials: (course) => request(`/api/materials${course ? `?course=${encodeURIComponent(course)}` : ''}`),
  getMaterial: (id) => request(`/api/materials/${id}`),
  uploadMaterial: (file, course) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('course', course)
    return request('/api/materials/upload', { method: 'POST', body: fd })
  },
  deleteMaterial: (id) => request(`/api/materials/${id}`, { method: 'DELETE' }),
  // 知识点
  listKps: (course) => request(`/api/knowledge-points${course ? `?course=${encodeURIComponent(course)}` : ''}`),
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
  wrongBook: (onlyUnresolved = true) => request(`/api/wrong-book?only_unresolved=${onlyUnresolved}`),
  updateWrong: (id, body) => request(`/api/wrong-book/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  // 统计
  statsOverview: () => request('/api/stats/overview'),
  // AI
  aiHealth: () => request('/api/health'),
  aiSummarize: (body) => request('/api/ai/summarize', { method: 'POST', body: JSON.stringify(body) }),
  aiAsk: (body) => request('/api/ai/ask', { method: 'POST', body: JSON.stringify(body) }),
  aiWeakAnalysis: (body) => request('/api/ai/weak-analysis', { method: 'POST', body: JSON.stringify(body) }),
}
