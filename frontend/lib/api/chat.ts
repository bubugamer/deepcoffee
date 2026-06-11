import type { CoffeaMessageRequest, CoffeaMessageResponse, DraftField } from '@/types'
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
