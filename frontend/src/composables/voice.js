// 语音输入组合式函数：说话 → 文字，供 AI 对话页的麦克风按钮用。
//
// 两级策略，自动挑可用的那个：
// 1. 浏览器自带语音识别（Web Speech API）：零配置、边说边出字。
//    只在 localhost / HTTPS 下存在，且 Chrome 走境外服务可能连不上。
// 2. 服务端识别：MediaRecorder 录音 → POST /api/ai/transcribe →
//    后端转发到 .env 里配的 OpenAI 兼容 ASR（如硅基流动 SenseVoice）。
// 两个都没有时返回明确的原因，界面提示用户怎么办。
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const SR = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null

export function useVoiceInput({ onText } = {}) {
  // idle 未开始 / listening 录音中 / processing 识别中
  const state = ref('idle')
  // 给界面看的说明：用的哪条路、为什么不能用
  const mode = ref(SR ? 'web' : 'server')
  const error = ref('')

  let rec = null
  let stream = null
  let recorder = null
  let chunks = []
  let onDone = null // 录音结束后的回调（server 模式用）

  function _emit(text, { final = false } = {}) {
    if (onText && text) onText(text, { final })
  }

  function _fail(msg) {
    error.value = msg
    state.value = 'idle'
    _cleanup()
    ElMessage.warning(msg)
  }

  function _cleanup() {
    try { rec && rec.abort() } catch { /* ignore */ }
    rec = null
    if (stream) {
      stream.getTracks().forEach((t) => t.stop())
      stream = null
    }
    recorder = null
    chunks = []
  }

  // ---------- 路 1：浏览器自带识别 ----------
  function startWeb() {
    const r = new SR()
    rec = r
    r.lang = 'zh-CN'
    r.continuous = true
    r.interimResults = true
    let finalText = ''
    let interim = ''
    r.onresult = (ev) => {
      interim = ''
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript
        if (ev.results[i].isFinal) finalText += t
        else interim += t
      }
      // 中间结果实时上屏，说错也看得见；final 之后由调用方落稿
      _emit(finalText + interim, { final: false })
    }
    r.onerror = (ev) => {
      const why = {
        'not-allowed': '麦克风权限被拒绝：浏览器地址栏左侧允许后重试',
        'service-not-allowed': '浏览器语音服务不可用（Chrome 需连境外网络），可改用 Edge 或配置服务端识别',
        network: '浏览器语音服务网络不通（Chrome 需连境外网络），可改用 Edge 或配置服务端识别',
        'no-speech': '',
      }[ev.error] || `语音识别出错：${ev.error}`
      if (why) _fail(why)
    }
    r.onend = () => {
      if (state.value !== 'listening') return
      state.value = 'idle'
      _cleanup()
      _emit(finalText.trim(), { final: true })
    }
    state.value = 'listening'
    try {
      r.start()
    } catch {
      _fail('语音识别启动失败，请重试')
    }
  }

  // ---------- 路 2：录音 → 服务端识别 ----------
  async function startRecord() {
    if (!navigator.mediaDevices?.getUserMedia) {
      _fail('当前页面不是 localhost/HTTPS，浏览器禁用了麦克风；用电脑打开（127.0.0.1）或配置 HTTPS')
      return
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      const why = e && e.name === 'NotAllowedError'
        ? '麦克风权限被拒绝：浏览器地址栏左侧允许后重试'
        : '拿不到麦克风：请检查设备连接'
      _fail(why)
      return
    }
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((m) => MediaRecorder.isTypeSupported(m))
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    chunks = []
    recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data)
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      stream = null
      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      chunks = []
      if (blob.size < 1200) {
        state.value = 'idle'
        ElMessage.info('没录到内容，按住说话的时间长一点')
        return
      }
      state.value = 'processing'
      try {
        const r = await api.transcribe(blob)
        state.value = 'idle'
        if (!r.text) {
          ElMessage.info('没听清，再说一遍试试')
          return
        }
        _emit(r.text, { final: true })
      } catch (e) {
        state.value = 'idle'
        ElMessage.error(e.message || '语音识别失败')
      }
    }
    state.value = 'listening'
    recorder.start()
  }

  function start(onFinish) {
    if (state.value !== 'idle') return
    error.value = ''
    onDone = onFinish || null
    if (SR) startWeb()
    else startRecord()
  }

  function stop() {
    if (state.value === 'listening') {
      if (rec) rec.stop() // onend 里收尾
      else if (recorder && recorder.state !== 'inactive') recorder.stop()
      else state.value = 'idle'
    }
  }

  function toggle(onFinish) {
    state.value === 'idle' ? start(onFinish) : stop()
  }

  return { state, mode, error, start, stop, toggle }
}
