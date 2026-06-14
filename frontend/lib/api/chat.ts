import type { ActionResult, CoffeaMessageRequest, CoffeaMessageResponse, DraftField } from '@/types'
import { apiFetch, isApiEnabled } from './client'

// ── Mock Data ─────────────────────────────────────────────────────────────
export const mockDraftFields: DraftField[] = [
  { label: '豆子',   value: '千峰庄园 帕卡马拉 CM 日晒' },
  { label: '器具',   value: 'V60', lowConf: true },
  { label: '磨豆机', value: 'Comandante C40' },
  { label: '研磨刻度', value: '#18' },
  { label: '豆重',   value: '15 g' },
  { label: '水量',   value: '225 ml（1:15）' },
  { label: '水温',   value: '92 °C' },
]

export const mockSuggestions: string[] = [
  '今天用 C40 #18 冲了千峰庄园帕卡马拉，15g 豆子，225ml 水，偏酸',
  'CM 处理法和普通日晒有什么区别？',
  '帮我查一下上次冲翡翠庄园的参数',
]

// ── Helpers ────────────────────────────────────────────────────────────────
// 图片 File → data URL（base64 内联）。vision 模型只收 base64，不收纯 URL。
export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error ?? new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })
}

// 上传前压缩：手机原图常有数 MB，等比缩到长边 ≤maxDim 并转 JPEG，
// 大幅减小请求体（弱网更不易卡住），对豆卡文字识别足够。解码失败则回退原图。
export async function compressImage(file: File, maxDim = 1600, quality = 0.82): Promise<string> {
  if (!file.type.startsWith('image/') || typeof document === 'undefined') {
    return fileToDataUrl(file)
  }
  try {
    const dataUrl = await fileToDataUrl(file)
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('decode failed'))
      el.src = dataUrl
    })
    const scale = Math.min(1, maxDim / Math.max(img.width, img.height))
    if (scale >= 1 && file.size <= 600_000) return dataUrl  // 已经够小，不折腾
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(img.width * scale)
    canvas.height = Math.round(img.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return dataUrl
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', quality)
  } catch {
    return fileToDataUrl(file)
  }
}

// ── API Functions ─────────────────────────────────────────────────────────
// POST /v1/coffea/messages —— 统一聊天入口（意图路由由后端完成，返回 results[]）
export async function sendCoffeaMessage(
  req: CoffeaMessageRequest,
  token?: string | null,
  signal?: AbortSignal,
): Promise<CoffeaMessageResponse> {
  if (isApiEnabled) {
    return apiFetch<CoffeaMessageResponse>('/coffea/messages', {
      method: 'POST',
      token,
      signal,
      body: JSON.stringify({
        message: req.message,
        session_id: req.session_id ?? null,
        attachments: req.attachments ?? [],
      }),
    })
  }
  return mockCoffeaResponse(req)
}

export interface CoffeaSessionTurn {
  role: 'user' | 'assistant'
  text?: string | null
  results?: ActionResult[]
  at?: number | null
  images?: string[]
}

export interface CoffeaSessionHistory {
  session_id: string
  state: Record<string, unknown>
  turns: CoffeaSessionTurn[]
}

// GET /coffea/session：该用户那条永久对话（跨设备同步）。失败/未启用返回 null，前端回退本地缓存。
export async function getCoffeaSession(token?: string | null): Promise<CoffeaSessionHistory | null> {
  if (!isApiEnabled) return null
  try {
    return await apiFetch<CoffeaSessionHistory>('/coffea/session', { token })
  } catch {
    return null
  }
}

function mockCoffeaResponse(req: CoffeaMessageRequest): CoffeaMessageResponse {
  const text = req.message
  const isKB = text.includes('处理法') || text.includes('知识') || text.includes('区别') || text.endsWith('？') || text.endsWith('?')
  const hasImage = (req.attachments ?? []).some((a) => a.type === 'image')
  const sessionId = req.session_id ?? `mock-coffea-${Date.now()}`

  if (isKB) {
    return {
      session_id: sessionId,
      primary_intent: 'kb_answer',
      secondary_intents: [],
      actions: [],
      results: [
        {
          type: 'web_verify',
          status: 'done',
          source: 'local',
          message: '已结合知识库与网络资料作答。',
          output: {
            sources: [
              { title: '处理法概览 · CM 二氧化碳浸渍法', url: 'https://example.com/cm', published_at: '2025-11-01' },
            ],
          },
        },
      ],
      state: {},
      reply:
        'CM（二氧化碳浸渍法）把整颗咖啡果密封在充满 CO₂ 的容器中完成厌氧发酵，相比普通日晒风味更集中、果汁感更强、可控性更高。',
      should_answer_directly: true,
      source: 'local',
      trace_id: 'fallback-coffea',
    }
  }

  // 默认当作冲煮记录意图
  return {
    session_id: sessionId,
    primary_intent: 'log_brew',
    secondary_intents: [],
    actions: [],
    results: [
      {
        type: 'log_brew',
        status: 'done',
        source: 'local',
        message: '已记录这次冲煮，并生成复盘建议。',
        output: { recap: '粉水比 1:15，#18 在 92°C 下萃取，尾段偏酸；建议调粗到 #19 并升温到 93–94°C。' },
      },
    ],
    state: { active_brew_id: 'mock-brew-1' },
    reply: hasImage ? '收到图片，已据此记录这次冲煮。' : '已记录这次冲煮。还想再问点什么吗？',
    should_answer_directly: false,
    source: 'local',
    trace_id: 'fallback-coffea',
  }
}
