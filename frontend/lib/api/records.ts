import type { BrewRecord, BrewComparisonItem } from '@/types'
import { ApiError, apiFetch, isApiEnabled } from './client'

// ── Mock Data ─────────────────────────────────────────────────────────────
export const mockRecords: BrewRecord[] = [
  {
    id: '1', user_id: 'mock', source_type: 'text',
    bean_card_id: 'bean-qianfeng-pacamara', record_type: 'brew', is_user_visible: true,
    bean_name: '千峰庄园 帕卡马拉 CM 日晒', origin: '巴拿马',
    roaster: 'Lighthouse 灯塔', process: 'CM 日晒', varietal: '帕卡马拉',
    device: 'V60', grinder: 'Comandante C40', grind_setting: '#18',
    dose_g: 15, water_ml: 225, ratio: '1:15', ratio_value: 15, water_temp_c: 92,
    brew_time: '2:35', brew_time_seconds: 155,
    brew_steps: [
      { time_seconds: 0,   action: '圆圈注水 闷蒸',       water_ml: 30  },
      { time_seconds: 30,  action: '断水等待',            water_ml: undefined },
      { time_seconds: 60,  action: '中心往外绕圈注水',    water_ml: 100 },
      { time_seconds: 100, action: '绕圈注水收尾',        water_ml: 95  },
    ],
    evaluation: {
      overall:    { score: 4, description: '果香明亮，有明显焦糖感，但尾段偏酸' },
      aroma:      { score: 4, description: '热带水果香，莓果前调明显' },
      flavor:     { score: 3, description: '中段焦糖甜感，尾段偏酸涩' },
      aftertaste: { score: 3, description: '余韵短，酸感略有残留' },
      acidity:    { score: 4, description: '明亮柠檬酸，略显尖锐' },
      body:       { score: 3, description: '中等醇厚，偏轻盈' },
      balance:    { score: 3, description: '前段与尾段不够平衡' },
    },
    notes: '果香明亮，有明显焦糖感，但尾段偏酸，发酵香较突出。粉床均匀，出汤稍快。',
    raw_input: '今天用 C40 #18 冲了千峰庄园的帕卡马拉 CM 日晒，15克豆子，225ml水，92度，感觉有点偏酸',
    recap: 'CM 日晒发酵度高，#18 偏细可能导致酸感集中在前段。建议下次试 #19，水温升至 93°C 观察甜感变化。',
    suggestions: ['研磨调粗到 #19，其他参数不变', '水温升至 93–94°C，提升甜感和萃取平衡度'],
    created_at: '2026-05-26T10:30:00Z', updated_at: '2026-05-26T10:30:00Z',
  },
  {
    id: '2', user_id: 'mock', source_type: 'text',
    bean_card_id: 'bean-esmeralda-geisha', record_type: 'brew', is_user_visible: true,
    bean_name: '翡翠庄园 瑰夏 水洗', origin: '巴拿马',
    device: 'V60', grinder: 'Comandante C40', grind_setting: '#20',
    dose_g: 15, water_ml: 240, ratio: '1:16', ratio_value: 16, water_temp_c: 94,
    brew_steps: [],
    evaluation: { overall: { score: 5, description: '干净花香，茉莉白桃，余韵悠长' } },
    notes: '干净花香，茉莉白桃，余韵悠长。',
    suggestions: [],
    created_at: '2026-05-25T09:00:00Z', updated_at: '2026-05-25T09:00:00Z',
  },
  {
    id: '3', user_id: 'mock', source_type: 'text',
    bean_card_id: 'bean-qianfeng-pacamara', record_type: 'brew', is_user_visible: true,
    bean_name: '千峰庄园 帕卡马拉 CM 日晒', origin: '巴拿马',
    device: 'V60', grinder: 'Comandante C40', grind_setting: '#19',
    dose_g: 15, water_ml: 225, ratio: '1:15', ratio_value: 15, water_temp_c: 93,
    brew_steps: [],
    evaluation: { overall: { score: 4, description: '比 #18 更平衡，焦糖甜感提升' } },
    notes: '比 #18 更平衡，焦糖甜感提升。',
    suggestions: [],
    created_at: '2026-05-20T11:00:00Z', updated_at: '2026-05-20T11:00:00Z',
  },
  {
    id: '4', user_id: 'mock', source_type: 'text',
    bean_card_id: 'bean-nicaragua-miskat', record_type: 'brew', is_user_visible: true,
    bean_name: '尼加拉瓜 蜜思卡特 日晒', origin: '尼加拉瓜',
    device: 'Aeropress', grinder: 'Timemore C2', grind_setting: '中细',
    dose_g: 18, water_ml: 250, ratio: '1:14', ratio_value: 14, water_temp_c: 88,
    brew_steps: [],
    evaluation: { overall: { score: 4, description: '浆果香浓，略显粗糙' } },
    notes: '浆果香浓，略显粗糙。',
    suggestions: [],
    created_at: '2026-05-22T14:00:00Z', updated_at: '2026-05-22T14:00:00Z',
  },
  {
    id: '5', user_id: 'mock', source_type: 'text',
    bean_card_id: 'bean-guatemala-huehue', record_type: 'brew', is_user_visible: true,
    bean_name: '危地马拉 薇薇特南戈 水洗', origin: '危地马拉',
    device: 'V60', grinder: 'Comandante C40', grind_setting: '#17',
    dose_g: 15, water_ml: 240, ratio: '1:16', ratio_value: 16, water_temp_c: 92,
    brew_steps: [],
    evaluation: { overall: { score: 4, description: '明亮柑橘酸，清爽干净' } },
    notes: '明亮柑橘酸，清爽干净。',
    suggestions: [],
    created_at: '2026-05-18T08:30:00Z', updated_at: '2026-05-18T08:30:00Z',
  },
]

const fallbackComparisons: Record<string, BrewComparisonItem[]> = {
  '千峰庄园 帕卡马拉 CM 日晒': [
    { id: '1', date: '5月26日', grinder: 'C40', grind_setting: '#18', dose_g: 15, water_ml: 225, water_temp_c: 92, overall_score: 4, active: true },
    { id: '3', date: '5月20日', grinder: 'C40', grind_setting: '#19', dose_g: 15, water_ml: 225, water_temp_c: 93, overall_score: 4, active: false },
    { id: '0', date: '5月15日', grinder: 'C40', grind_setting: '#18', dose_g: 15, water_ml: 220, water_temp_c: 91, overall_score: 3, active: false },
  ],
}

// ── API Functions ─────────────────────────────────────────────────────────
export interface BrewRecordFilters {
  bean?: string
  q?: string
  device?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}

function filterFallbackRecords(filters: BrewRecordFilters = {}) {
  return mockRecords.filter((record) => {
    if (filters.bean && record.bean_name !== filters.bean) return false
    if (filters.device && record.device !== filters.device) return false
    if (filters.q) {
      const needle = filters.q.toLowerCase()
      const haystack = [
        record.bean_name,
        record.origin,
        record.roaster,
        record.varietal,
        record.device,
        record.grinder,
        record.notes,
        record.raw_input,
      ].filter(Boolean).join(' ').toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })
}

// GET /v1/brew/records
export async function getRecords(filters: BrewRecordFilters = {}, token?: string | null): Promise<BrewRecord[]> {
  if (isApiEnabled) {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
    })
    const qs = params.toString()
    const res = await apiFetch<{ items: BrewRecord[] }>(`/brew/records${qs ? `?${qs}` : ''}`, { token })
    return res.items
  }
  return filterFallbackRecords(filters)
}

// GET /v1/brew/records/:id
export async function getRecord(id: string, token?: string | null): Promise<BrewRecord | null> {
  if (isApiEnabled) {
    try {
      return await apiFetch<BrewRecord>(`/brew/records/${id}`, { token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
  return mockRecords.find(r => r.id === id) ?? null
}

// GET /v1/brew/compare?bean_name=...
export async function getComparisons(beanName: string, token?: string | null): Promise<BrewComparisonItem[]> {
  if (isApiEnabled) {
    return apiFetch<BrewComparisonItem[]>(`/brew/compare?bean_name=${encodeURIComponent(beanName)}`, { token })
  }
  return fallbackComparisons[beanName] ?? []
}

// POST /v1/brew/parse
export async function parseBrewInput(input: string): Promise<{
  draft: Record<string, unknown>
  confidence: number
  low_confidence_fields: string[]
  clarification?: string
  trace_id: string
}> {
  return apiFetch('/brew/parse', {
    method: 'POST',
    body: JSON.stringify({ input, source_type: 'text' }),
  })
}

// POST /v1/brew/confirm
export async function confirmBrew(draft: Record<string, unknown>, rawInput?: string, beanCardId?: string, token?: string | null): Promise<{
  brew_id: string
  recap: string
  suggestions: string[]
  trace_id: string
}> {
  return apiFetch('/brew/confirm', {
    method: 'POST',
    token,
    body: JSON.stringify({ draft, source_type: 'text', raw_input: rawInput, bean_card_id: beanCardId }),
  })
}

// DELETE /v1/brew/records/:id
export async function deleteRecord(id: string): Promise<void> {
  await apiFetch(`/brew/records/${id}`, { method: 'DELETE' })
}
