import type {
  Bean,
  BeanConfirmResponse,
  BeanDraft,
  BrewEvaluation,
  BeanParseResponse,
  BeanRecommendedParams,
  BeanSquareImportResponse,
  BeanSquareItem,
  RecommendationParams,
  RecommendParamsResponse,
  RecommendParamsTurnResponse,
} from '@/types'
import { ApiError, apiFetch, isApiEnabled } from './client'
import { mockRecords } from './records'

export interface BeanFilters {
  q?: string
  process?: string
  min_score?: number
}

const DEFAULT_FLAVOR = {
  notes: ['花香', '果味', '甜感'],
  source: 'default' as const,
  scale_max: 5,
  axes: [],
}

const DEFAULT_RATING = null

const FALLBACK_FLAVORS: Record<string, Bean['flavor']> = {
  '千峰庄园 帕卡马拉 CM 日晒': {
    notes: ['热带水果', '莓果', '焦糖'],
    source: 'default',
    scale_max: 5,
    axes: [
      { label: '酸质', value: 4 },
      { label: '甜感', value: 3 },
      { label: '醇厚', value: 3 },
      { label: '余韵', value: 4 },
      { label: '发酵感', value: 4 },
    ],
  },
  '翡翠庄园 瑰夏 水洗': {
    notes: ['茉莉花香', '柑橘', '白桃'],
    source: 'roaster',
    scale_max: 5,
    axes: [
      { label: '酸度', value: 3 },
      { label: '甜度', value: 4 },
      { label: '花香', value: 5 },
      { label: '果汁感', value: 4 },
      { label: '干净度', value: 5 },
      { label: '余韵', value: 4 },
    ],
  },
  '尼加拉瓜 蜜思卡特 日晒': {
    notes: ['浆果', '草莓', '甜香料'],
    source: 'default',
    scale_max: 5,
    axes: [
      { label: '酸质', value: 3 },
      { label: '甜感', value: 4 },
      { label: '醇厚', value: 3 },
      { label: '余韵', value: 3 },
      { label: '发酵感', value: 3 },
    ],
  },
  '危地马拉 薇薇特南戈 水洗': {
    notes: ['柑橘', '红苹果', '坚果'],
    source: 'default',
    scale_max: 5,
    axes: [
      { label: '酸质', value: 4 },
      { label: '甜感', value: 3 },
      { label: '醇厚', value: 2 },
      { label: '余韵', value: 3 },
      { label: '发酵感', value: 1 },
    ],
  },
}

function secondsToRatio(recordId: string): BeanRecommendedParams | null {
  const record = mockRecords.find((item) => item.id === recordId)
  if (!record) return null
  return {
    record_id: record.id,
    record_type: record.record_type ?? 'brew',
    device: record.device,
    grinder: record.grinder,
    grind_setting: record.grind_setting,
    dose_g: record.dose_g,
    water_ml: record.water_ml,
    water_temp_c: record.water_temp_c,
    ratio: record.ratio,
    ratio_value: record.ratio_value,
    brew_time_seconds: record.brew_time_seconds,
  }
}

function fallbackBeans(): Bean[] {
  const groups = new Map<string, typeof mockRecords>()

  mockRecords.forEach((record) => {
    const key = record.bean_card_id ?? record.bean_name ?? record.id
    const existing = groups.get(key) ?? []
    existing.push(record)
    groups.set(key, existing)
  })

  return Array.from(groups.entries()).map(([beanId, records]) => {
    const first = records[0]
    const name = first.bean_name ?? '未命名豆卡'
    const scored = records.filter((record) => record.evaluation?.overall?.score != null)
    const avgScore = scored.length
      ? Math.round(scored.reduce((sum, record) => sum + (record.evaluation?.overall?.score ?? 0), 0) / scored.length * 10) / 10
      : null
    const recommended = records[0]?.id ? secondsToRatio(records[0].id) : null

    return {
      bean_id: beanId,
      name,
      roaster: first.roaster ?? null,
      roaster_product: name,
      coffee_source: name.includes('庄园') ? name.split(' ')[0] : null,
      green_bean_merchant: null,
      green_bean_product: null,
      origin: first.origin ?? null,
      process: first.process ?? null,
      varietal: first.varietal ? [first.varietal] : [],
      altitude_text: null,
      harvest_date_text: null,
      roast_date_text: null,
      net_weight_text: null,
      bean_components: [],
      bean_product_type: 'single',
      flavor: FALLBACK_FLAVORS[name] ?? DEFAULT_FLAVOR,
      rating: DEFAULT_RATING,
      private_notes: null,
      public_comment: null,
      recommended_record_id: recommended?.record_id ?? null,
      recommended_params: recommended,
      avg_score: avgScore,
      record_count: records.length,
      created_at: first.created_at,
      updated_at: first.updated_at,
    }
  })
}

function filterFallbackBeans(filters: BeanFilters = {}) {
  const q = filters.q?.trim().toLowerCase()
  return fallbackBeans().filter((bean) => {
    if (filters.process && bean.process !== filters.process) return false
    if (filters.min_score && (bean.avg_score == null || bean.avg_score < filters.min_score)) return false
    if (!q) return true
    const haystack = [
      bean.name,
      bean.roaster,
      bean.roaster_product,
      bean.coffee_source,
      bean.green_bean_merchant,
      bean.green_bean_product,
      bean.origin,
      bean.process,
      ...bean.varietal,
    ].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(q)
  })
}

function fallbackDraft(input: string): BeanDraft {
  const roaster = input.match(/(光合烘焙|Lighthouse|灯塔|Seesaw|M Stand|明谦|治光师)/)?.[0]
  const origin = input.match(/(巴拿马|哥伦比亚|埃塞俄比亚|尼加拉瓜|危地马拉|肯尼亚|云南)/)?.[0]
  const process = input.match(/(CM\s*日晒|厌氧日晒|水洗|日晒|蜜处理|半水洗|厌氧)/)?.[0]?.replace(/\s+/g, ' ')
  const varietal = input.match(/(瑰夏|Geisha|Gesha|帕卡马拉|Pacamara|铁皮卡|Typica|波旁|Bourbon|卡杜拉|Caturra)/)?.[0]
  const source = input.match(/[\u4e00-\u9fa5A-Za-z0-9]+庄园/)?.[0]
  const nameParts = [source, varietal, process].filter(Boolean)

  return {
    name: nameParts.length ? nameParts.join(' ') : input.slice(0, 24),
    roaster_name: roaster,
    roaster_product_name: nameParts.length ? nameParts.join(' ') : undefined,
    bean_components: [{
      origin_name: origin,
      coffee_source_name: source,
      process_name: process,
      varietal_names: varietal ? [varietal] : [],
    }],
    flavor: DEFAULT_FLAVOR,
    private_notes: input,
    public_comment: undefined,
  }
}

// GET /v1/beans
export async function getBeans(filters: BeanFilters = {}, token?: string | null): Promise<Bean[]> {
  if (isApiEnabled) {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
    })
    const qs = params.toString()
    const res = await apiFetch<{ items: Bean[]; total: number }>(`/beans${qs ? `?${qs}` : ''}`, { token })
    return res.items
  }
  return filterFallbackBeans(filters)
}

// GET /v1/beans/:id
export async function getBean(beanId: string, token?: string | null): Promise<Bean | null> {
  if (isApiEnabled) {
    try {
      return await apiFetch<Bean>(`/beans/${beanId}`, { token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
  return fallbackBeans().find((bean) => bean.bean_id === beanId) ?? null
}

export async function getBeanSquare(filters: BeanFilters = {}, token?: string | null): Promise<BeanSquareItem[]> {
  if (isApiEnabled) {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
    })
    const qs = params.toString()
    const res = await apiFetch<{ items: BeanSquareItem[]; total: number }>(`/beans/square${qs ? `?${qs}` : ''}`, { token })
    return res.items
  }
  return filterFallbackBeans(filters).map((bean) => ({
    ...bean,
    owner_count: 1,
    comments: [],
    public_comment: bean.public_comment ?? '这支豆子的风味信息可以作为冲煮参考。',
  }))
}

export async function getBeanSquareDetail(beanId: string, token?: string | null): Promise<BeanSquareItem | null> {
  if (isApiEnabled) {
    try {
      return await apiFetch<BeanSquareItem>(`/beans/square/${beanId}`, { token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
  return (await getBeanSquare({}, token)).find((bean) => bean.bean_id === beanId) ?? null
}

export async function importBeanSquare(beanIds: string[], token?: string | null): Promise<BeanSquareImportResponse> {
  if (isApiEnabled) {
    return apiFetch<BeanSquareImportResponse>('/beans/square/import', {
      method: 'POST',
      token,
      body: JSON.stringify({ bean_ids: beanIds }),
    })
  }
  return {
    items: beanIds.map((beanId, index) => ({
      source_bean_id: beanId,
      bean_id: `fallback-import-${index}-${beanId}`,
      status: 'created',
    })),
    created_count: beanIds.length,
    existing_count: 0,
  }
}

// POST /v1/beans/parse
export async function parseBeanInput(input: string, token?: string | null): Promise<BeanParseResponse> {
  if (isApiEnabled) {
    return apiFetch<BeanParseResponse>('/beans/parse', {
      method: 'POST',
      token,
      body: JSON.stringify({ input, source_type: 'text' }),
    })
  }
  return {
    draft: fallbackDraft(input),
    confidence: 0.72,
    low_confidence_fields: ['roaster_name', 'bean_components.0.origin_name', 'bean_components.0.process_name'].filter((field) => {
      const draft = fallbackDraft(input)
      if (field === 'bean_components.0.origin_name') return !draft.bean_components?.[0]?.origin_name
      if (field === 'bean_components.0.process_name') return !draft.bean_components?.[0]?.process_name
      return !draft[field as keyof BeanDraft]
    }),
    clarification: null,
    trace_id: 'fallback-bean-parse',
  }
}

// POST /v1/beans/confirm
export async function confirmBean(
  draft: BeanDraft,
  rawInput?: string,
  token?: string | null,
  sourceType: string = 'text',
): Promise<BeanConfirmResponse> {
  if (isApiEnabled) {
    return apiFetch<BeanConfirmResponse>('/beans/confirm', {
      method: 'POST',
      token,
      body: JSON.stringify({ draft, source_type: sourceType, raw_input: rawInput }),
    })
  }
  return {
    bean_id: `fallback-${Date.now()}`,
    trace_id: 'fallback-bean-confirm',
  }
}

// PATCH /v1/beans/:id
export type BeanUpdateInput = Omit<Partial<BeanDraft>, 'name'> & { rating?: BrewEvaluation | null }

export async function updateBean(beanId: string, draft: BeanUpdateInput, token?: string | null): Promise<Bean> {
  if (isApiEnabled) {
    return apiFetch<Bean>(`/beans/${beanId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(draft),
    })
  }
  const existing = await getBean(beanId, token)
  if (!existing) throw new ApiError(404, 'not_found', '豆卡不存在')
  const nextComponents = draft.bean_components ?? existing.bean_components
  const singleSource = nextComponents.length === 1 ? nextComponents[0] : null
  return {
    ...existing,
    roaster: draft.roaster_name ?? existing.roaster,
    roaster_product: draft.roaster_product_name ?? existing.roaster_product,
    coffee_source: draft.bean_components ? singleSource?.coffee_source_name ?? null : existing.coffee_source,
    green_bean_merchant: draft.bean_components ? singleSource?.green_bean_merchant_name ?? null : existing.green_bean_merchant,
    green_bean_product: draft.bean_components ? singleSource?.green_bean_product_name ?? null : existing.green_bean_product,
    origin: draft.bean_components ? singleSource?.origin_name ?? null : existing.origin,
    process: draft.bean_components ? singleSource?.process_name ?? null : existing.process,
    varietal: draft.bean_components ? singleSource?.varietal_names ?? [] : existing.varietal,
    altitude_text: draft.bean_components ? singleSource?.altitude_text ?? null : existing.altitude_text,
    harvest_date_text: draft.bean_components ? singleSource?.harvest_date_text ?? null : existing.harvest_date_text,
    roast_date_text: draft.roast_date_text ?? existing.roast_date_text,
    net_weight_text: draft.net_weight_text ?? existing.net_weight_text,
    bean_components: nextComponents,
    flavor: draft.flavor ?? existing.flavor,
    rating: Object.prototype.hasOwnProperty.call(draft, 'rating') ? draft.rating ?? null : existing.rating,
    private_notes: draft.private_notes ?? existing.private_notes,
    public_comment: draft.public_comment ?? existing.public_comment,
  }
}

// POST /v1/beans/:id/recommend-params —— 多轮：先追问器具，补全后给出建议参数
export async function recommendParamsTurn(
  beanId: string,
  body: { session_id?: string | null; message?: string | null } = {},
  token?: string | null,
): Promise<RecommendParamsTurnResponse> {
  if (isApiEnabled) {
    return apiFetch<RecommendParamsTurnResponse>(`/beans/${beanId}/recommend-params`, {
      method: 'POST',
      token,
      body: JSON.stringify({
        session_id: body.session_id ?? null,
        message: body.message ?? null,
      }),
    })
  }
  // Mock 多轮：首轮（无 message）先追问器具，补充后再给建议
  const sessionId = body.session_id ?? `mock-rec-${Date.now()}`
  if (!body.message?.trim()) {
    return {
      status: 'needs_input',
      assistant_message: '好的，我来帮你定这支豆子的冲煮参数。你打算用什么冲煮器具、磨豆机和过滤介质？例如「V60 + Comandante C40 + 纸滤」。',
      session_id: sessionId,
      equipment: {},
      missing_fields: ['dripper', 'grinder', 'filter_media'],
      source: 'local',
      trace_id: 'fallback-recommend-turn',
    }
  }
  const base = secondsToRatio('1')
  return {
    status: 'completed',
    assistant_message: '根据你的器具和这支豆子的处理法，我建议下面这组参数，已为你保存到豆卡。',
    session_id: sessionId,
    equipment: { dripper: 'V60', grinder: 'Comandante C40', filter_media: '纸滤' },
    missing_fields: [],
    recommendation: {
      device: base?.device ?? 'V60',
      grinder: base?.grinder ?? 'Comandante C40',
      grind_setting: base?.grind_setting ?? '#19',
      dose_g: base?.dose_g ?? 15,
      water_ml: base?.water_ml ?? 225,
      water_temp_c: base?.water_temp_c ?? 93,
      ratio: base?.ratio ?? '1:15',
      brew_time_seconds: base?.brew_time_seconds ?? 155,
      filter: '漂白滤纸',
      notes: 'CM 日晒发酵度高，水温略高有助甜感。',
    },
    recommended_record_id: base?.record_id ?? 'fallback-ai',
    source: 'local',
    trace_id: 'fallback-recommend-turn',
  }
}

// 把多轮返回的 recommendation 映射成豆卡展示用的 BeanRecommendedParams
export function recommendationToBeanParams(
  rec: RecommendationParams,
  recordId?: string | null,
): BeanRecommendedParams {
  return {
    record_id: recordId ?? 'ai_suggestion',
    record_type: 'ai_suggestion',
    device: rec.device ?? undefined,
    grinder: rec.grinder ?? undefined,
    grind_setting: rec.grind_setting ?? undefined,
    filter_media: rec.filter ?? undefined,
    dose_g: rec.dose_g ?? undefined,
    water_ml: rec.water_ml ?? undefined,
    water_temp_c: rec.water_temp_c ?? undefined,
    ratio: rec.ratio ?? undefined,
    brew_time_seconds: rec.brew_time_seconds ?? undefined,
  }
}

// 手动编辑的建议参数（豆卡详情页编辑模式）；后端落成隐藏 user_suggestion 记录
export interface ManualRecommendParams {
  brew_method?: string
  device?: string
  grinder?: string
  grind_setting?: string
  filter_media?: string
  water?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  // 粉水比由后端按豆量/水量自动换算（与冲煮记录一致），前端不再手填提交。
  brew_time_seconds?: number
  notes?: string
}

// PUT /v1/beans/:id/recommend-params（手动参数路径）
export async function setManualRecommendParams(
  beanId: string,
  params: ManualRecommendParams,
  token?: string | null,
): Promise<RecommendParamsResponse> {
  return apiFetch<RecommendParamsResponse>(`/beans/${beanId}/recommend-params`, {
    method: 'PUT',
    token,
    body: JSON.stringify({ params }),
  })
}

// PUT /v1/beans/:id/recommend-params
export async function setRecommendedParams(beanId: string, recordId: string, token?: string | null): Promise<RecommendParamsResponse> {
  if (isApiEnabled) {
    return apiFetch<RecommendParamsResponse>(`/beans/${beanId}/recommend-params`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ record_id: recordId }),
    })
  }
  const recommended = secondsToRatio(recordId) ?? secondsToRatio('1')
  if (!recommended) throw new ApiError(404, 'not_found', '冲煮记录不存在')
  return {
    recommended_params: recommended,
    recommended_record_id: recordId,
    trace_id: 'fallback-set-recommend-params',
  }
}
