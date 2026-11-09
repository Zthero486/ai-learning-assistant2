// AI 对话核心逻辑：浮窗 AiChat 和各页面内嵌 AiInline 共用。
// 含 SSE 事件处理、工具步骤卡片、AI→UI 联动跳转（navigate + 出题直通自测）。
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

export const TOOL_LABEL = {
  list_syllabus: '查看教材目录',
  find_node: '定位章节',
  search_content: '检索史料',
  read_material: '阅读原文',
  list_knowledge_points: '查知识点',
  list_events: '查时间轴',
  get_my_stats: '看学习数据',
  get_wrong_book: '看错题',
  navigate: '切换页面',
  create_knowledge_point: '写入知识点',
  create_material: '生成资料',
  create_questions: '生成题目',
  create_task: '建复习任务',
  create_event: '补时间轴',
  tag_wrong_error: '标注错因',
  save_memory: '沉淀记忆',
  list_memory: '查记忆库',
  delete_task: '删除任务',
  delete_knowledge_point: '删知识点',
  delete_material: '删资料',
  delete_event: '删时间轴事件',
  delete_question: '删题目',
  delete_memory: '删记忆',
  clear_wrong_book: '清空错题本',
  __review__: '质量自查',
}

// AI 动作 → 页面：写入类工具完成后顺势带学生去对应板块
const UI_ROUTE = {
  create_knowledge_point: '/knowledge',
  create_questions: '/practice',
  create_task: '/tasks',
  create_material: '/materials',
  create_event: '/timeline',
  tag_wrong_error: '/wrong-book',
}

export function toolLabel(name) {
  return TOOL_LABEL[name] || name
}

// 工具入参的一行预览（轨迹里展示 AI 到底传了什么，而不是只说「调了什么」）
function argText(args) {
  if (!args || typeof args !== 'object') return ''
  const parts = []
  for (const [k, v] of Object.entries(args)) {
    if (v === null || v === undefined || v === '') continue
    let s = typeof v === 'string' ? v : JSON.stringify(v)
    if (s.length > 36) s = s.slice(0, 36) + '…'
    parts.push(`${k}=${s}`)
    if (parts.join(', ').length > 60) break
  }
  return parts.join(', ').slice(0, 80)
}

/**
 * @param {Object} o
 * @param {import('vue').Ref} o.msgs          消息数组（调用方持有，共享历史）
 * @param {import('vue').Ref} o.busy
 * @param {import('vue').Ref} o.controller    AbortController ref
 * @param {Function} o.persist               历史落 localStorage
 * @param {Function} o.getAllowWrite         是否允许写入
 * @param {Function} o.getUiLink             是否联动跳转
 * @param {Function} [o.getPageContext]      返回页面上下文字符串（内嵌模式用）
 * @param {Function} [o.onNavigated]         联动跳转后的回调（浮窗用它收起面板）
 */
export function useAiConversation(o) {
  const router = useRouter()

  async function send(text) {
    const content = (text ?? '').trim()
    if (!content || o.busy.value) return
    o.msgs.value.push({ role: 'user', content })
    const reply = { role: 'assistant', content: '', steps: [], trace: [], pending: true,
                    startAt: Date.now() }
    o.msgs.value.push(reply)
    o.busy.value = true
    o.controller.value = new AbortController()

    const history = o.msgs.value
      .filter((m) => !m.pending && m.content)
      .map((m) => ({ role: m.role, content: m.content }))
      .slice(-20)

    // 本轮 AI 新出的题：done 时合并成一次「去自测页开做」的跳转，避免多批次互相覆盖
    const freshQids = []

    try {
      await api.aiChat(
        {
          messages: history,
          allow_write: o.getAllowWrite(),
          stream: true,
          page_context: o.getPageContext ? o.getPageContext() : '',
        },
        {
          signal: o.controller.value.signal,
          onEvent: (ev) => {
            if (ev.type === 'thinking') {
              // 模型round内的中间想法（它打算先查什么/先做什么）
              reply.trace.push({ kind: 'think', round: ev.round, text: ev.text || '' })
            } else if (ev.type === 'state' && !ev.reason) {
              reply.trace.push({ kind: 'state', state: ev.state, round: ev.round })
              if (ev.state === 'review') {
                reply.steps.push({ tool: '__review__', summary: '正在自查结果是否满足要求…', ok: null })
              }
            } else if (ev.type === 'step' && ev.phase === 'start') {
              reply.steps.push({ tool: ev.tool, summary: '执行中…', ok: null, write: !!ev.write })
              reply.trace.push({
                kind: 'tool', tool: ev.tool, round: ev.round, write: !!ev.write,
                argText: argText(ev.args), summary: '执行中…', ok: null, ms: null,
              })
            } else if (ev.type === 'step' && ev.phase === 'end') {
              // 从后往前找第一条同名的「执行中」，避免并行调用时串位
              for (let i = reply.steps.length - 1; i >= 0; i--) {
                if (reply.steps[i].tool === ev.tool && reply.steps[i].ok === null) {
                  reply.steps[i].summary = ev.summary
                  reply.steps[i].ok = ev.ok
                  break
                }
              }
              for (let i = reply.trace.length - 1; i >= 0; i--) {
                const t = reply.trace[i]
                if (t.kind === 'tool' && t.tool === ev.tool && t.ok === null) {
                  t.summary = ev.summary
                  t.ok = ev.ok
                  t.ms = ev.ms
                  break
                }
              }
              // AI→UI 联动：工具成功后按映射切页面（navigate 是显式指令，其余是写完顺势带你去看）
              if (ev.ok && o.getUiLink()) {
                const ui = ev.detail?.ui || {}
                const target = ui.route || UI_ROUTE[ev.tool]
                // 出题特殊：先攒着 id，done 时统一跳（同轮多批合并成一轮新题会话）
                if (ev.tool === 'create_questions' && !ui.route) {
                  freshQids.push(...(ev.detail?.ids || []))
                } else if (target && ui.query) {
                  // 带参数跳（如教材页 ?node=xx&hl=原文：翻到指定节并临时标注）
                  router.push({ path: target, query: ui.query })
                  o.onNavigated?.(target)
                } else if (target && router.currentRoute.value.path !== target) {
                  router.push(target)
                  o.onNavigated?.(target)
                }
              }
            } else if (ev.type === 'state' && ev.state === 'act' && ev.reason) {
              // 审查不达标回流：把自查卡片标黄并写明缺口，继续执行
              reply.trace.push({ kind: 'reflow', reason: ev.reason, round: ev.round })
              for (let i = reply.steps.length - 1; i >= 0; i--) {
                if (reply.steps[i].tool === '__review__' && reply.steps[i].ok === null) {
                  reply.steps[i].summary = `自查未达标（${ev.reason}），继续执行`
                  reply.steps[i].ok = true
                  break
                }
              }
            } else if (ev.type === 'error') {
              reply.content = `⚠ ${ev.message}`
              reply.pending = false
            } else if (ev.type === 'done') {
              // 还挂着的自查卡片 = 审查通过收尾
              for (const s of reply.steps) {
                if (s.tool === '__review__' && s.ok === null) s.summary = '自查通过'
                if (s.ok === null) s.ok = true
              }
              for (const t of reply.trace) {
                if (t.kind === 'tool' && t.ok === null) { t.ok = true; t.summary = t.summary || '已完成' }
              }
              reply.elapsedMs = ev.elapsed_ms || (reply.startAt ? Date.now() - reply.startAt : 0)
              reply.content = ev.reply || reply.content || '（AI 没有返回内容，换个说法再问一次试试）'
              reply.pending = false
              // 出完题统一带路：人已在自测页也要触发，所以 query 每次都变
              if (freshQids.length && o.getUiLink()) {
                router.push({ path: '/practice', query: { fresh: freshQids.join(',') } })
                o.onNavigated?.('/practice')
              }
              if (ev.mode === 'unavailable') {
                ElMessage.warning('当前没有可用的 AI Key，请先在「AI 设置」里配置')
              }
            }
          },
        },
      )
    } catch (e) {
      if (e.name === 'AbortError') {
        reply.content = reply.content || '（已停止）'
      } else {
        reply.content = `⚠ ${e.message}`
        ElMessage.error(e.message)
      }
      reply.pending = false
    } finally {
      o.busy.value = false
      o.controller.value = null
      reply.pending = false
      o.persist?.()
    }
  }

  function stop() {
    o.controller.value?.abort()
    o.busy.value = false
  }

  return { send, stop }
}
