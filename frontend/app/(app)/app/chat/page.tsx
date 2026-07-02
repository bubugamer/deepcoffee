'use client'
import { useState, useRef, useEffect, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  Send, AlertTriangle, AlertCircle, CheckCircle2, Clock,
  ImagePlus, X, Globe, Square, Plus, Trash2,
} from 'lucide-react'
import { confirmBean, getBeans, getBeanEntityCatalog } from '@/lib/api/beans'
import {
  createEquipment,
  getEquipmentCatalog,
  listEquipment,
  type EquipmentCatalogItem,
  type EquipmentCategory,
  type EquipmentProfile,
} from '@/lib/api/equipment'
import { Combobox, type ComboOption } from '@/components/Combobox'
import { entityCatalogOptions, beanFieldSuggestions, type BeanFieldSuggestions } from '@/lib/beans'

const EMPTY_BEAN_SUGGESTIONS: BeanFieldSuggestions = { processes: [], origins: [], varietals: [], roasters: [] }
import { softValidate, type FieldKind } from '@/lib/validate'
import { confirmBrew } from '@/lib/api/records'
import {
  sendCoffeaMessage,
  getCoffeaSession,
  patchCoffeaSessionResult,
  compressImage,
  mockSuggestions,
} from '@/lib/api/chat'
import { isQuotaExceeded } from '@/lib/api/client'
import { QuotaNotice } from '@/components/QuotaNotice'
import { ChatMarkdown } from '@/components/ChatMarkdown'
import ImageLightbox from '@/components/ImageLightbox'
import { useProfile } from '@/components/ProfileContext'
import { getToken } from '@/lib/auth'
import { isExternalSourceHref, sourceHref } from '@/lib/knowledge-source-links'
import type {
  Bean, BeanDraft, BeanComponent, ActionResult, ActionStatus, CoffeaAttachment, WebVerifySource,
} from '@/types'

const BREW_HINTS = [
  '今天用 V60 冲了翡翠庄园瑰夏，15g 粉，225ml，93°C，2:40，甜感很好',
  'C40 #18，千峰庄园帕卡马拉 CM 日晒，15g，225ml，1:15，92°C',
]

const BEAN_GUIDE_HINTS = [
  '新入手：光合烘焙翡翠庄园瑰夏，水洗处理，巴拿马，还没开袋',
  '刚拿到千峰庄园帕卡马拉 CM 日晒，想先建个档案',
]

// 向导模式（AI 新增豆卡 / 记录）的开场引导语——第一句由 AI 说，告诉用户按什么格式描述。
const BEAN_WIZARD_GUIDE = '好的，我来帮你建立豆卡 🫘\n\n告诉我豆子的基本信息就行——烘焙商、豆名、产区、处理法、品种，想附上烘焙日期、购入渠道也可以。可以照下面的例子说：'
const BREW_WIZARD_GUIDE = '好的，来记这杯冲煮 ☕️\n\n把冲煮参数发我就行——豆子、粉量、水量、水温、时间、研磨刻度，有风味感受也可以一起说。可以照下面的例子说：'

function beanComponentHasContent(component: BeanComponent): boolean {
  return Boolean(
    component.origin_name?.trim()
      || component.coffee_source_name?.trim()
      || component.green_bean_merchant_name?.trim()
      || component.green_bean_product_name?.trim()
      || component.process_name?.trim()
      || component.altitude_text?.trim()
      || component.harvest_date_text?.trim()
      || component.share_text?.trim()
      || component.notes?.trim()
      || (component.varietal_names ?? []).some(item => item.trim()),
  )
}

function sanitizeBeanDraft(draft: BeanDraft): BeanDraft {
  return {
    ...draft,
    bean_components: (draft.bean_components ?? []).filter(beanComponentHasContent),
  }
}

// ── Shared sub-components ─────────────────────────────────
function TypingDots() {
  return (
    <div className="flex gap-1 items-center px-4 py-3 bg-white border border-dc-border rounded-2xl rounded-tl-sm w-fit">
      {[0, 1, 2].map(i => (
        <div
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-dc-text-3 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: '1.2s' }}
        />
      ))}
    </div>
  )
}

function AiAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-dc-accent-light flex-shrink-0 overflow-hidden border border-dc-border">
      <img src="/logo.png" alt="DC" className="w-full h-full object-contain p-0.5" />
    </div>
  )
}

function UserAvatar() {
  // 与侧边栏一致：取账户的 display_name / 邮箱首字符，不硬编码
  const { profile } = useProfile()
  const name = profile?.display_name ?? profile?.email ?? ''
  return (
    <div className="w-8 h-8 rounded-full bg-dc-text-1 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">
      {name.charAt(0).toUpperCase() || '我'}
    </div>
  )
}

// ── Coffea action result rendering ───────────────────────
const ACTION_LABEL: Record<string, string> = {
  log_brew: '记录冲煮',
  parse_brew: '解析冲煮',
  log_bean: '建立豆卡',
  parse_bean: '解析豆卡',
  kb_answer: '知识库',
  knowledge: '知识库',
  knowledge_answer: '知识库',
  web_verify: '联网核实',
  recommend_params: '建议参数',
  recommend_brew_params: '建议参数',
  compare: '冲煮对比',
  read_bean_card_image: '豆卡识别',
  assess_brew_photo: '冲煮照片',
  adjust_brew_params: '参数调整',
  scale_recipe: '配方换算',
  grinder_conversion: '研磨换算',
  storage_resting_advice: '储存养豆',
  equipment_advice: '器具建议',
  equipment_capture: '记录器具',
  brew_record_parse: '记录冲煮',
  create_or_update_bean_card: '豆卡',
}

function statusMeta(status: ActionStatus) {
  switch (status) {
    case 'done':     return { label: '完成',    cls: 'bg-dc-green-bg text-dc-green border-green-200',  Icon: CheckCircle2 }
    case 'degraded': return { label: '部分完成', cls: 'bg-dc-yellow-bg text-dc-yellow border-yellow-200', Icon: AlertCircle }
    case 'pending':  return { label: '处理中',  cls: 'bg-dc-subtle text-dc-text-2 border-dc-border',    Icon: Clock }
    case 'failed':   return { label: '失败',    cls: 'bg-red-50 text-dc-red border-red-200',           Icon: AlertTriangle }
  }
}

function getSources(output?: Record<string, unknown> | null): WebVerifySource[] {
  const raw = output?.sources
  if (!Array.isArray(raw)) return []
  return raw.filter((s): s is WebVerifySource => typeof s === 'object' && s !== null)
}

// 「正文型」回答（与后端 coffea_executor._ANSWER_TYPES 对应）：其综合正文已并入顶层 reply，
// 卡片只展示来源链接、不再重复正文。其余类型（如待确认引导）的正文不进 reply，仍在卡片显示。
const ANSWER_RESULT_TYPES = new Set([
  'knowledge_answer',
  'web_verify',
  'direct_answer',
  'recommend_brew_params',
  'adjust_brew_params',
  'scale_recipe',
  'grinder_conversion',
  'storage_resting_advice',
  'equipment_advice',
])

function ActionResultCard({ result, replyText }: { result: ActionResult; replyText?: string | null }) {
  const meta = statusMeta(result.status)
  const { Icon } = meta
  // 动作名只显示中文标签；未知类型一律「处理结果」，绝不裸显内部英文动作名
  const label = ACTION_LABEL[result.type] ?? '处理结果'
  const sources = getSources(result.output)
  // 正文型回答已在 reply 里、不在卡片重复；正文已并入 reply（合并多答案）时也用包含判断兜住。
  // 原始 output JSON 不展示给用户。
  const message = result.message?.trim()
  const inReply = !!message && !!replyText && replyText.trim().includes(message)
  const showMessage = !!message && !ANSWER_RESULT_TYPES.has(result.type) && !inReply
  if (!showMessage && sources.length === 0) return null

  return (
    <div className="dc-card overflow-hidden text-sm">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-dc-border bg-dc-subtle/40">
        <span className="font-medium text-dc-text-1">{label}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded border flex items-center gap-1 ${meta.cls}`}>
          <Icon size={11} /> {meta.label}
        </span>
      </div>
      <div className="px-3 py-2.5 space-y-2">
        {showMessage && (
          <div className="text-dc-text-2 leading-relaxed">
            <ChatMarkdown text={message} />
          </div>
        )}

        {sources.length > 0 && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1 text-xs text-dc-text-3">
              <Globe size={11} /> 参考来源
            </div>
            {sources.map((s, i) => {
              const href = sourceHref(s)
              const subtitle = s.url ?? s.excerpt
              const time = s.published_at ?? s.time
              const content = (
                <>
                  <div className="text-dc-text-1 font-medium line-clamp-1">{s.title ?? href ?? '参考来源'}</div>
                  {(subtitle || time) && (
                    <div className="text-xs text-dc-text-3 line-clamp-1">
                      {subtitle}{subtitle && time ? ` · ${time}` : time}
                    </div>
                  )}
                </>
              )
              const className = 'block rounded-lg border border-dc-border px-2.5 py-1.5 hover:border-dc-accent-hi transition-colors'

              if (!href) {
                return <div key={i} className={className}>{content}</div>
              }

              if (isExternalSourceHref(href)) {
                return (
                  <a key={i} href={href} target="_blank" rel="noopener noreferrer" className={className}>
                    {content}
                  </a>
                )
              }

              return (
                <Link key={i} href={href} className={className}>
                  {content}
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

type ResultPatchFn = (patch: Record<string, unknown>, message?: string) => void | Promise<void>

// ── 聊天内豆卡草稿确认（read_bean_card_image 低识别度路径）──
function ChatBeanDraft({
  result,
  onPatch,
}: {
  result: ActionResult
  onPatch: ResultPatchFn
}) {
  const output = result.output ?? {}
  const savedBeanId = typeof output.saved_bean_id === 'string' ? output.saved_bean_id : null
  const [draft, setDraft] = useState<BeanDraft>(() => (output.draft as BeanDraft) ?? {})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  // 烘焙商/产地/处理法/品种下拉：吃公共实体目录 ∪ 用户已有值，和表单一致。
  const [suggestions, setSuggestions] = useState<BeanFieldSuggestions>(EMPTY_BEAN_SUGGESTIONS)
  useEffect(() => {
    let cancelled = false
    const token = getToken()
    Promise.all([getBeans({}, token).catch(() => []), getBeanEntityCatalog(token)])
      .then(([beans, catalog]) => { if (!cancelled) setSuggestions(beanFieldSuggestions(beans, catalog)) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  if (output.dismissed === true) {
    return (
      <div className="dc-card px-4 py-3 text-sm text-dc-text-3">
        已忽略这张豆卡草稿
      </div>
    )
  }
  if (savedBeanId) {
    return (
      <div className="dc-card px-4 py-3 flex items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-1.5 text-dc-green">
          <CheckCircle2 size={14} /> 已保存到豆仓
        </span>
        <Link href={`/app/beans/${savedBeanId}`} className="text-dc-accent hover:underline text-xs">
          查看豆卡 →
        </Link>
      </div>
    )
  }

  const confidence = typeof output.confidence === 'number' ? output.confidence : null

  async function confirm() {
    setSaving(true)
    setError('')
    try {
      const rawInput = typeof output.raw_input === 'string' ? output.raw_input : undefined
      const source = result.type === 'create_or_update_bean_card' ? 'text' : 'image'
      const res = await confirmBean(sanitizeBeanDraft(draft), rawInput, getToken(), source)
      await onPatch({ saved_bean_id: res.bean_id }, '已保存到豆仓。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <BeanDraftCard
      draft={draft}
      confidence={confidence}
      lowConfidenceFields={[]}
      clarification={null}
      error={error}
      saving={saving}
      suggestions={suggestions}
      onChange={setDraft}
      onConfirm={confirm}
      onRetry={() => void onPatch({ dismissed: true }, '已忽略这张豆卡草稿。')}
      retryLabel="忽略"
    />
  )
}

// ── 聊天内冲煮草稿确认（brew_record_parse 解析出参数后）──
const BREW_TEXT_FIELDS: { key: string; label: string; placeholder: string; kind?: FieldKind }[] = [
  { key: 'grind_setting', label: '研磨刻度', placeholder: '例如：4.8 圈' },
  { key: 'dose_g', label: '粉量 (g)', placeholder: '15', kind: 'number' },
  { key: 'water_ml', label: '水量 (ml)', placeholder: '270', kind: 'number' },
  { key: 'water_temp_c', label: '水温 (°C)', placeholder: '96', kind: 'number' },
  { key: 'ratio', label: '粉水比', placeholder: '1:18' },
  { key: 'time', label: '时间', placeholder: '2:30 或 150（秒）', kind: 'time' },
]

const CUSTOM = '__custom__'
const BREW_METHODS = ['滤杯冲煮', '意式', '法压壶', '爱乐压', '浸泡式', '摩卡壶', '虹吸壶', '冷萃']
const EQUIPMENT_CATEGORY_LABEL: Record<EquipmentCategory, string> = {
  brewer: '冲煮器具',
  grinder: '磨豆机',
  filter_media: '过滤介质',
  water: '用水',
}

// 可搜索下拉（来源：豆仓 / 我的器具 / 公共器具目录，按 label + 别名模糊匹配）+ 自由输入兜底。
// choice 存已选项的 value（豆子是 bean_id、器具是名字）或 CUSTOM；custom 存自由输入文本。
function ComboField({
  label, missing, options, choice, custom, placeholder, onChoice, onCustom,
}: {
  label: string
  missing: boolean
  options: ComboOption[]
  choice: string
  custom: string
  placeholder: string
  onChoice: (v: string) => void
  onCustom: (v: string) => void
}) {
  const isCustom = choice === CUSTOM
  const displayValue = isCustom ? custom : (options.find(o => o.value === choice)?.label ?? '')
  const empty = choice === '' || (isCustom && !custom.trim())
  const highlight = missing && empty
  return (
    <div className="block">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-dc-text-3">
          {label}{highlight && <span className="text-dc-yellow ml-1">待补充</span>}
        </span>
      </div>
      <Combobox
        options={options}
        value={displayValue}
        placeholder={placeholder}
        highlight={highlight}
        onInput={t => { onChoice(CUSTOM); onCustom(t) }}
        onSelect={v => { onChoice(v); onCustom('') }}
      />
    </div>
  )
}

function parseBrewTimeText(text: string): number | undefined {
  const t = text.trim()
  if (!t) return undefined
  const m = t.match(/^(\d+)[:：](\d{1,2})$/)
  if (m) return Number(m[1]) * 60 + Number(m[2])
  const n = Number(t)
  return Number.isFinite(n) && n > 0 ? Math.round(n) : undefined
}

function ChatBrewDraft({
  result, linkedBeanId, onPatch,
}: {
  result: ActionResult
  linkedBeanId: string | null
  onPatch: ResultPatchFn
}) {
  const output = result.output ?? {}
  const savedRecordId = typeof output.saved_record_id === 'string' ? output.saved_record_id : null
  const savedRecap = typeof output.saved_recap === 'string' ? output.saved_recap : null
  const savedBeanId = typeof output.saved_bean_id === 'string' ? output.saved_bean_id : null
  const savedBeanName = typeof output.saved_bean_name === 'string' ? output.saved_bean_name : null
  const baseDraft = (output.draft as Record<string, unknown>) ?? {}
  const missing = Array.isArray(output.missing_fields) ? (output.missing_fields as string[]) : []
  const steps = Array.isArray(baseDraft.brew_steps) ? baseDraft.brew_steps : []
  const parsedBeanName = String(baseDraft.bean_name ?? '').trim()
  const parsedBrewMethod = String(baseDraft.brew_method ?? '').trim()
  const parsedDevice = String(baseDraft.device ?? '').trim()
  const parsedGrinder = String(baseDraft.grinder ?? '').trim()
  const parsedFilterMedia = String(baseDraft.filter_media ?? '').trim()
  const parsedWater = String(baseDraft.water ?? '').trim()

  // 下拉数据源：豆仓 + 我的器具 + 公共器具目录；拉取失败回退为纯手输（空选项 + 自定义）
  const [beans, setBeans] = useState<Bean[] | null>(null)
  const [equipment, setEquipment] = useState<EquipmentProfile[] | null>(null)
  const [catalog, setCatalog] = useState<Record<string, EquipmentCatalogItem[]> | null>(null)
  // 补齐新豆的处理法下拉：吃公共实体目录（规范名 + 别名），拉取失败回退纯手输。
  const [processOptions, setProcessOptions] = useState<ComboOption[]>([])
  const resolvedBeanId = typeof output.resolved_bean_id === 'string' ? output.resolved_bean_id : null
  const [beanChoice, setBeanChoice] = useState(parsedBeanName ? CUSTOM : '')
  const [beanCustom, setBeanCustom] = useState(parsedBeanName)
  const [brewMethod, setBrewMethod] = useState(parsedBrewMethod)
  const [device, setDevice] = useState({ choice: parsedDevice ? CUSTOM : '', custom: parsedDevice })
  const [grinder, setGrinder] = useState({ choice: parsedGrinder ? CUSTOM : '', custom: parsedGrinder })
  const [filterMedia, setFilterMedia] = useState({ choice: parsedFilterMedia ? CUSTOM : '', custom: parsedFilterMedia })
  const [water, setWater] = useState({ choice: parsedWater ? CUSTOM : '', custom: parsedWater })
  const [fields, setFields] = useState<Record<string, string>>(() => ({
    grind_setting: String(baseDraft.grind_setting ?? ''),
    dose_g: baseDraft.dose_g != null ? String(baseDraft.dose_g) : '',
    water_ml: baseDraft.water_ml != null ? String(baseDraft.water_ml) : '',
    water_temp_c: baseDraft.water_temp_c != null ? String(baseDraft.water_temp_c) : '',
    ratio: String(baseDraft.ratio ?? ''),
    time: typeof baseDraft.brew_time_seconds === 'number'
      ? `${Math.floor(baseDraft.brew_time_seconds / 60)}:${String(baseDraft.brew_time_seconds % 60).padStart(2, '0')}`
      : String(baseDraft.brew_time ?? ''),
  }))
  // 记一杯「新豆」（豆仓里没有）时，必须现场补齐建豆卡的必填项（烘焙商/产地/处理法），
  // 从冲煮草稿里已解析到的同名字段预填，避免「先提交、后端才报缺字段、又无处可填」的死胡同。
  const [newBean, setNewBean] = useState({
    roaster: typeof baseDraft.roaster === 'string' ? baseDraft.roaster : '',
    origin: typeof baseDraft.origin === 'string' ? baseDraft.origin : '',
    process: typeof baseDraft.process === 'string' ? baseDraft.process : '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const beanInitRef = useRef(false)
  const equipInitRef = useRef(false)
  // 记录用户已手动改过的字段：异步数据到位后的「自动预选」只填没被碰过的，避免覆盖用户刚做的修改
  //（慢网/后端冷启动下，数据晚到几秒会把用户先改的豆子/器具又盖回解析值或默认值）。
  const touchedRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    getBeans({}, getToken())
      .then(list => { if (!cancelled) setBeans(list) })
      .catch(() => { if (!cancelled) setBeans([]) })
    listEquipment()
      .then(list => { if (!cancelled) setEquipment(list) })
      .catch(() => { if (!cancelled) setEquipment([]) })
    getEquipmentCatalog()
      .then(c => { if (!cancelled) setCatalog(c) })
      .catch(() => { if (!cancelled) setCatalog({}) })
    getBeanEntityCatalog(getToken())
      .then(c => { if (!cancelled) setProcessOptions(entityCatalogOptions(c.process)) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  // 豆仓就绪后预选：后端已解析的 resolved_bean_id 优先，其次豆卡页的 linkedBeanId，再次解析名精确同名；
  // 未命中保持自定义预填（后端 post-pass 已把解析名改写成豆卡全名，精确同名通常即可命中）。
  useEffect(() => {
    if (beans === null || beanInitRef.current) return
    beanInitRef.current = true
    if (touchedRef.current.has('bean')) return  // 用户已手动改过豆子，不覆盖
    const preferredId = [resolvedBeanId, linkedBeanId].find(id => id && beans.some(b => b.bean_id === id))
    if (preferredId) {
      setBeanChoice(preferredId)
      return
    }
    const match = parsedBeanName ? beans.find(b => b.name.trim() === parsedBeanName) : undefined
    if (match) setBeanChoice(match.bean_id)
  }, [beans, resolvedBeanId, linkedBeanId, parsedBeanName])

  // 器具就绪后预选：解析值命中选项（目录 ∪ 我的器具）即选中；解析为空时取各类别默认项。
  // 等器具与目录都到位再预选一次，避免目录后到导致漏选。
  useEffect(() => {
    if (equipment === null || catalog === null || equipInitRef.current) return
    equipInitRef.current = true
    const names = (category: EquipmentCategory) =>
      Array.from(new Set([...(catalog[category] ?? []).map(c => c.name), ...equipment.filter(e => e.category === category).map(e => e.name)]))
    const def = (category: EquipmentCategory) => equipment.find(e => e.category === category && e.is_default)
    const drippers = names('brewer')
    const grinders = names('grinder')
    const filters = names('filter_media')
    const waters = names('water')
    // 各字段的自动预选只在用户没手动改过时生效（touchedRef 守卫），避免覆盖用户刚做的修改。
    if (!touchedRef.current.has('device')) setDevice(cur => {
      if (parsedDevice && drippers.includes(parsedDevice)) return { choice: parsedDevice, custom: '' }
      if (!parsedDevice && def('brewer')?.name) return { choice: def('brewer')!.name, custom: '' }
      return cur
    })
    if (!touchedRef.current.has('grinder')) setGrinder(cur => {
      if (parsedGrinder && grinders.includes(parsedGrinder)) return { choice: parsedGrinder, custom: '' }
      if (!parsedGrinder && def('grinder')?.name) return { choice: def('grinder')!.name, custom: '' }
      return cur
    })
    if (!touchedRef.current.has('filter')) setFilterMedia(cur => {
      if (parsedFilterMedia && filters.includes(parsedFilterMedia)) return { choice: parsedFilterMedia, custom: '' }
      if (!parsedFilterMedia && def('filter_media')?.name) return { choice: def('filter_media')!.name, custom: '' }
      return cur
    })
    if (!touchedRef.current.has('water')) setWater(cur => {
      if (parsedWater && waters.includes(parsedWater)) return { choice: parsedWater, custom: '' }
      if (!parsedWater && def('water')?.name) return { choice: def('water')!.name, custom: '' }
      return cur
    })
  }, [equipment, catalog, parsedDevice, parsedGrinder, parsedFilterMedia, parsedWater])

  if (output.dismissed === true) {
    return (
      <div className="dc-card px-4 py-3 text-sm text-dc-text-3">
        已忽略这条冲煮记录草稿
      </div>
    )
  }
  if (savedRecordId) {
    return (
      <div className="dc-card px-4 py-3 text-sm space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-dc-green">
            <CheckCircle2 size={14} /> 已保存到冲煮记录
          </span>
          <Link href={`/app/records/${savedRecordId}`} className="text-dc-accent hover:underline text-xs">
            查看记录 →
          </Link>
        </div>
        {savedBeanId && (
          <div className="flex items-center justify-between gap-2 text-xs text-dc-text-3">
            <span>已为「{savedBeanName ?? '新豆子'}」建豆卡并关联</span>
            <Link href={`/app/beans/${savedBeanId}`} className="text-dc-accent hover:underline">查看豆卡 →</Link>
          </div>
        )}
        {savedRecap && <p className="text-xs text-dc-text-3 leading-relaxed">{savedRecap}</p>}
      </div>
    )
  }

  const beanOptions = (beans ?? []).map(b => ({ value: b.bean_id, label: b.name }))
  const uniq = (values: (string | null | undefined)[]) => [...new Set(values.filter(Boolean) as string[])]
  // 下拉选项 = 公共器具目录（带别名）∪ 我的器具（去重）；可搜索 + 自由输入兜底。
  const byCategory = (category: EquipmentCategory): ComboOption[] => {
    const catItems = catalog?.[category] ?? []
    const aliasOf = new Map(catItems.map(c => [c.name, c.aliases]))
    return uniq([...catItems.map(c => c.name), ...(equipment ?? []).filter(e => e.category === category).map(e => e.name)])
      .map(v => ({ value: v, label: v, aliases: aliasOf.get(v) }))
  }
  const deviceOptions = byCategory('brewer')
  const grinderOptions = byCategory('grinder')
  const filterOptions = byCategory('filter_media')
  const waterOptions = byCategory('water')

  // 手输豆名且豆仓里没有同名豆 → 需现场补齐豆卡必填项后再建卡
  const customBeanName = beanChoice === CUSTOM ? beanCustom.trim() : ''
  const customUnmatched = !!customBeanName && !(beans ?? []).some(b => b.name.trim() === customBeanName)
  // 新豆的三个必填项齐了才允许保存（豆仓里已有的豆或选了现有豆卡则无需）
  const newBeanReady = !customUnmatched || Boolean(newBean.roaster.trim() && newBean.origin.trim() && newBean.process.trim())

  async function confirm() {
    setSaving(true)
    setError('')
    try {
      const token = getToken()
      const rawInput = typeof output.raw_input === 'string' ? output.raw_input : undefined

      // 1) 确保一张豆卡（每条冲煮记录必须关联豆卡）：选现有 → 同名匹配 → 否则自动建一张最简卡。
      let beanCardId: string | undefined
      let beanName: string | undefined
      let createdBeanId: string | undefined
      if (beanChoice && beanChoice !== CUSTOM) {
        beanCardId = beanChoice
        beanName = (beans ?? []).find(b => b.bean_id === beanChoice)?.name
      } else {
        const typedName = customBeanName || (typeof baseDraft.bean_name === 'string' ? baseDraft.bean_name.trim() : '')
        beanName = typedName || undefined
        const match = typedName ? (beans ?? []).find(b => b.name.trim() === typedName) : undefined
        if (match) {
          beanCardId = match.bean_id
        } else {
          // 无匹配豆卡 → 用用户现场补齐的必填项（烘焙商/产地/处理法）建档，保证后端不会因缺字段打回。
          const draftBean: BeanDraft = {
            name: typedName || undefined,
            roaster_name: newBean.roaster.trim() || undefined,
            bean_components: [{
              origin_name: newBean.origin.trim() || undefined,
              process_name: newBean.process.trim() || undefined,
              varietal_names: typeof baseDraft.varietal === 'string' ? [baseDraft.varietal] : [],
            }],
          }
          const created = await confirmBean(sanitizeBeanDraft(draftBean), rawInput, token)
          beanCardId = created.bean_id
          createdBeanId = created.bean_id
        }
      }

      const numeric = (text: string) => {
        const n = Number(text.trim())
        return text.trim() && Number.isFinite(n) && n > 0 ? n : undefined
      }
      const deviceValue = device.choice === CUSTOM ? device.custom.trim() : device.choice
      const grinderValue = grinder.choice === CUSTOM ? grinder.custom.trim() : grinder.choice
      const filterValue = filterMedia.choice === CUSTOM ? filterMedia.custom.trim() : filterMedia.choice
      const waterValue = water.choice === CUSTOM ? water.custom.trim() : water.choice
      // 2) 在解析草稿基础上合并用户编辑（注水步骤等其余字段原样保留）
      const merged: Record<string, unknown> = {
        ...baseDraft,
        bean_name: beanName,
        brew_method: brewMethod || undefined,
        device: deviceValue || undefined,
        grinder: grinderValue || undefined,
        grind_setting: fields.grind_setting.trim() || undefined,
        filter_media: filterValue || undefined,
        water: waterValue || undefined,
        dose_g: numeric(fields.dose_g),
        water_ml: numeric(fields.water_ml),
        water_temp_c: numeric(fields.water_temp_c),
        ratio: fields.ratio.trim() || undefined,
        brew_time_seconds: parseBrewTimeText(fields.time),
      }
      const res = await confirmBrew(merged, rawInput, beanCardId, token)
      await onPatch({
        saved_record_id: res.brew_id,
        saved_recap: res.recap,
        ...(createdBeanId ? { saved_bean_id: createdBeanId, saved_bean_name: beanName } : {}),
      }, '已保存到冲煮记录。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dc-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dc-border">
        <span className="text-sm font-semibold text-dc-text-1">冲煮记录草稿</span>
        {steps.length > 0 && (
          <span className="text-xs text-dc-text-3">已解析 {steps.length} 段注水</span>
        )}
      </div>
      <div className="p-4 grid sm:grid-cols-2 gap-3">
        <div>
          <ComboField
            label="豆子"
            missing={missing.includes('bean_name')}
            options={beanOptions}
            choice={beanChoice}
            custom={beanCustom}
            placeholder="例如：千峰庄园帕卡马拉"
            onChoice={v => { touchedRef.current.add('bean'); setBeanChoice(v) }}
            onCustom={v => { touchedRef.current.add('bean'); setBeanCustom(v) }}
          />
          {customUnmatched && (
            <div className="mt-2 rounded-lg border border-dc-border bg-dc-subtle/50 p-3 space-y-2">
              <p className="text-xs text-dc-text-3">豆仓里还没有这支豆，保存时会为它建一张豆卡。请补齐豆卡必填信息：</p>
              <label className="block">
                <span className="text-xs text-dc-text-3 mb-1 block">烘焙商 <span className="text-dc-red">*</span></span>
                <input
                  value={newBean.roaster}
                  onChange={e => setNewBean(c => ({ ...c, roaster: e.target.value }))}
                  placeholder="例如：光合作用"
                  className="dc-input text-sm py-1.5"
                />
              </label>
              <label className="block">
                <span className="text-xs text-dc-text-3 mb-1 block">产地 <span className="text-dc-red">*</span></span>
                <input
                  value={newBean.origin}
                  onChange={e => setNewBean(c => ({ ...c, origin: e.target.value }))}
                  placeholder="例如：埃塞俄比亚耶加雪菲"
                  className="dc-input text-sm py-1.5"
                />
              </label>
              <div className="block">
                <span className="text-xs text-dc-text-3 mb-1 block">处理法 <span className="text-dc-red">*</span></span>
                <Combobox
                  options={processOptions}
                  value={newBean.process}
                  placeholder="输入或选择处理法"
                  onInput={v => setNewBean(c => ({ ...c, process: v }))}
                  onSelect={v => setNewBean(c => ({ ...c, process: v }))}
                />
              </div>
            </div>
          )}
        </div>
        <label className="block">
          <span className="text-xs text-dc-text-3 mb-1 block">冲煮方式</span>
          <select
            value={brewMethod}
            onChange={e => setBrewMethod(e.target.value)}
            className="dc-input text-sm py-1.5"
          >
            <option value="">未选择</option>
            {BREW_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <ComboField
          label="滤杯"
          missing={missing.includes('device')}
          options={deviceOptions}
          choice={device.choice}
          custom={device.custom}
          placeholder="例如：V60"
          onChoice={v => { touchedRef.current.add('device'); setDevice(cur => ({ ...cur, choice: v })) }}
          onCustom={v => { touchedRef.current.add('device'); setDevice(cur => ({ ...cur, custom: v })) }}
        />
        <ComboField
          label="磨豆机"
          missing={missing.includes('grinder')}
          options={grinderOptions}
          choice={grinder.choice}
          custom={grinder.custom}
          placeholder="例如：ZP6S"
          onChoice={v => { touchedRef.current.add('grinder'); setGrinder(cur => ({ ...cur, choice: v })) }}
          onCustom={v => { touchedRef.current.add('grinder'); setGrinder(cur => ({ ...cur, custom: v })) }}
        />
        <ComboField
          label="过滤介质"
          missing={missing.includes('filter_media')}
          options={filterOptions}
          choice={filterMedia.choice}
          custom={filterMedia.custom}
          placeholder="例如：纸滤"
          onChoice={v => { touchedRef.current.add('filter'); setFilterMedia(cur => ({ ...cur, choice: v })) }}
          onCustom={v => { touchedRef.current.add('filter'); setFilterMedia(cur => ({ ...cur, custom: v })) }}
        />
        <ComboField
          label="用水"
          missing={missing.includes('water')}
          options={waterOptions}
          choice={water.choice}
          custom={water.custom}
          placeholder="例如：农夫山泉"
          onChoice={v => { touchedRef.current.add('water'); setWater(cur => ({ ...cur, choice: v })) }}
          onCustom={v => { touchedRef.current.add('water'); setWater(cur => ({ ...cur, custom: v })) }}
        />
        {BREW_TEXT_FIELDS.map(({ key, label, placeholder, kind }) => {
          const isMissing = (key === 'time' ? missing.includes('brew_time_seconds') : missing.includes(key))
            && !fields[key].trim()
          const warning = softValidate(kind, fields[key])
          return (
            <label key={key} className="block">
              <span className="text-xs text-dc-text-3 mb-1 block">
                {label}{isMissing && <span className="text-dc-yellow ml-1">待补充</span>}
              </span>
              <input
                value={fields[key]}
                onChange={e => setFields(cur => ({ ...cur, [key]: e.target.value }))}
                placeholder={placeholder}
                className={`dc-input text-sm py-1.5 ${isMissing ? 'border-dc-yellow bg-dc-yellow-bg/50' : warning ? 'border-dc-yellow' : ''}`}
              />
              {warning && <p className="text-xs text-dc-yellow mt-1">{warning}</p>}
            </label>
          )
        })}
      </div>
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-100 text-xs text-dc-red">{error}</div>
      )}
      <div className="px-4 py-3 border-t border-dc-border flex gap-2">
        <button
          onClick={confirm}
          disabled={saving || !newBeanReady}
          className="btn-primary text-sm py-2 flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '保存中…' : !newBeanReady ? '补齐豆卡必填项后保存' : '确认保存'}
        </button>
        <button onClick={() => void onPatch({ dismissed: true }, '已忽略这条冲煮记录草稿。')} className="btn-secondary text-sm py-2">忽略</button>
      </div>
    </div>
  )
}

type EquipmentDraftItem = {
  category: EquipmentCategory
  name: string
  notes?: string | null
}

function isEquipmentCategory(value: unknown): value is EquipmentCategory {
  return value === 'brewer' || value === 'grinder' || value === 'filter_media' || value === 'water'
}

function normalizeEquipmentDraftItems(raw: unknown): EquipmentDraftItem[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const items: EquipmentDraftItem[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object') continue
    const obj = row as Record<string, unknown>
    const category = obj.category
    const name = typeof obj.name === 'string' ? obj.name.trim() : ''
    if (!isEquipmentCategory(category) || !name) continue
    const key = `${category}:${name.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    items.push({
      category,
      name,
      notes: typeof obj.notes === 'string' ? obj.notes : '',
    })
  }
  return items
}

function ChatEquipmentDraft({
  result,
  onPatch,
}: {
  result: ActionResult
  onPatch: ResultPatchFn
}) {
  const output = result.output ?? {}
  const [items, setItems] = useState<EquipmentDraftItem[]>(() => normalizeEquipmentDraftItems(output.items))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  if (output.dismissed === true) {
    return (
      <div className="dc-card px-4 py-3 text-sm text-dc-text-3">
        已忽略这组器具草稿
      </div>
    )
  }
  if (output.saved === true) {
    const savedCount = typeof output.saved_count === 'number' ? output.saved_count : items.length
    return (
      <div className="dc-card px-4 py-3 flex items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-1.5 text-dc-green">
          <CheckCircle2 size={14} /> 已保存 {savedCount} 件器具
        </span>
        <Link href="/app/equipment" className="text-dc-accent hover:underline text-xs">
          查看器具 →
        </Link>
      </div>
    )
  }
  if (items.length === 0) return null

  function updateItem(index: number, patch: Partial<EquipmentDraftItem>) {
    setItems(cur => cur.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  async function confirm() {
    const validItems = items
      .map(item => ({ ...item, name: item.name.trim(), notes: item.notes?.trim() ?? '' }))
      .filter(item => item.name)
    if (validItems.length === 0) return
    setSaving(true)
    setError('')
    try {
      for (const item of validItems) {
        await createEquipment({
          category: item.category,
          name: item.name,
          notes: item.notes || undefined,
        })
      }
      await onPatch({ saved: true, saved_count: validItems.length }, `已保存 ${validItems.length} 件器具。`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dc-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dc-border">
        <span className="text-sm font-semibold text-dc-text-1">器具草稿</span>
        <span className="text-xs text-dc-text-3">{items.length} 件</span>
      </div>
      <div className="p-4 space-y-3">
        {items.map((item, index) => (
          <div key={`${item.category}:${index}`} className="grid sm:grid-cols-[130px,1fr] gap-2">
            <select
              value={item.category}
              onChange={e => updateItem(index, { category: e.target.value as EquipmentCategory })}
              className="dc-input text-sm py-1.5"
            >
              {(Object.keys(EQUIPMENT_CATEGORY_LABEL) as EquipmentCategory[]).map(category => (
                <option key={category} value={category}>{EQUIPMENT_CATEGORY_LABEL[category]}</option>
              ))}
            </select>
            <div className="flex gap-2">
              <input
                value={item.name}
                onChange={e => updateItem(index, { name: e.target.value })}
                className="dc-input text-sm py-1.5 flex-1"
                placeholder="器具名称"
              />
              <button
                type="button"
                onClick={() => setItems(cur => cur.filter((_, i) => i !== index))}
                className="btn-secondary text-sm px-3 py-1.5"
              >
                移除
              </button>
            </div>
            <div className="hidden sm:block" />
            <input
              value={item.notes ?? ''}
              onChange={e => updateItem(index, { notes: e.target.value })}
              className="dc-input text-sm py-1.5"
              placeholder="备注，可选"
            />
          </div>
        ))}
      </div>
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-100 text-xs text-dc-red">{error}</div>
      )}
      <div className="px-4 py-3 border-t border-dc-border flex gap-2">
        <button
          onClick={confirm}
          disabled={saving || items.every(item => !item.name.trim())}
          className="btn-primary text-sm py-2 flex-1 disabled:opacity-50"
        >
          {saving ? '保存中…' : '确认保存'}
        </button>
        <button onClick={() => void onPatch({ dismissed: true }, '已忽略这组器具草稿。')} className="btn-secondary text-sm py-2">忽略</button>
      </div>
    </div>
  )
}

// 自动录入成功的简洁结果卡（消息正文已说明，卡片只给入口）
function AutoSavedBeanCard({ beanId }: { beanId: string }) {
  return (
    <div className="dc-card px-4 py-3 flex items-center justify-between gap-2 text-sm">
      <span className="flex items-center gap-1.5 text-dc-green">
        <CheckCircle2 size={14} /> 已录入豆仓
      </span>
      <Link href={`/app/beans/${beanId}`} className="text-dc-accent hover:underline text-xs">
        查看豆卡 →
      </Link>
    </div>
  )
}

// 追问卡（追问体系）：一句提示 + 快捷回复。带 message 的回复调 send 发出去；message 为空则本地关闭。
function BrewRecordOffer({ result, onSend }: { result: ActionResult; onSend: (text: string) => void }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  const output = (result.output ?? {}) as { prompt?: string; replies?: { label?: string; message?: string | null }[] }
  const prompt = output.prompt ?? '要顺手记录一次冲煮吗？'
  const replies = Array.isArray(output.replies) ? output.replies : []
  return (
    <div className="dc-card px-4 py-3 text-sm">
      <p className="text-dc-text-2 mb-2.5">{prompt}</p>
      <div className="flex flex-wrap gap-2">
        {replies.map((rep, i) => (
          <button
            key={i}
            onClick={() => { if (rep.message) onSend(rep.message); else setDismissed(true) }}
            className={
              rep.message
                ? 'btn-primary text-xs px-3.5 py-1.5'
                : 'text-xs px-3.5 py-1.5 rounded-full border border-dc-border text-dc-text-2 hover:border-dc-accent-hi bg-white'
            }
          >
            {rep.label ?? '好的'}
          </button>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// Coffea 真实对话线程（通用聊天 + 冲煮记录）
// ─────────────────────────────────────────────────────────
interface ChatTurn {
  role: 'user' | 'assistant'
  text?: string | null
  images?: string[]          // data URL 预览
  results?: ActionResult[]
  pending?: boolean
  error?: string
  quota?: boolean            // 402 ai_quota_exceeded：展示升级引导而非报错红条
  at?: number                // epoch ms；微信式居中时间戳用（旧持久化数据可能没有）
}

// 微信式时间格式：今天 HH:mm；昨天；今年 M月D日；更早带年份
function formatChatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const hm = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return hm
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${hm}`
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}

const TIME_GAP_MS = 5 * 60 * 1000  // 与上一条带时间消息间隔超 5 分钟才显示（仿微信）

function TimeDivider({ at }: { at: number }) {
  return (
    <div className="flex justify-center">
      <span className="text-[11px] text-dc-text-3 bg-dc-subtle px-2.5 py-1 rounded-full">
        {formatChatTime(at)}
      </span>
    </div>
  )
}

function dataUrlMime(d: string): string | undefined {
  return d.match(/^data:([^;]+);/)?.[1]
}

// 历史会话持久化：按用户 id 各存一份（localStorage，本机，离线兜底）。
// 图片不进 localStorage（体积大）：图片走服务端图床，历史回看时由服务端 URL 提供。
const CHAT_STORE_VERSION = 1
const MAX_STORED_TURNS = 60

function chatStorageKey(userId: string): string {
  return `dc_chat_${userId}`
}

function persistTurns(key: string, sessionId: string | null, turns: ChatTurn[]) {
  try {
    const slim = turns
      .filter(t => !t.pending)
      .slice(-MAX_STORED_TURNS)
      .map(({ images: _images, ...rest }) => rest)
    localStorage.setItem(key, JSON.stringify({ v: CHAT_STORE_VERSION, sessionId, turns: slim }))
  } catch { /* 存储满 / 隐私模式：静默放弃持久化 */ }
}

function CoffeaChat({ newMode, linkedBeanId }: { newMode: string | null; linkedBeanId: string | null }) {
  // 向导入口：记录（?new=1）/ 豆卡（?new=bean）。向导不载历史、AI 先开口，但对话仍并入同一条会话。
  const isBrew = newMode === '1'
  const isBean = newMode === 'bean'
  const isWizard = isBrew || isBean
  const { profile } = useProfile()
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [pendingImages, setPendingImages] = useState<string[]>([])
  const [preparingImages, setPreparingImages] = useState(false)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)  // 点击放大查看的聊天图片
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const msgsRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  // restoredRef 置 true 后才开始写盘，避免「先用空数组覆盖了已存的历史」
  const restoredRef = useRef(false)

  const storageKey = profile ? chatStorageKey(profile.id) : null

  // 挂载时加载该用户那条永久对话：服务端为唯一真相（跨设备同步），失败回退本地缓存。
  // 向导模式（记录 / 建豆卡）例外：不载历史，只 seed 一条 AI 引导语（客户端合成、不入服务端会话）；
  // 仍取回 sessionId 让本轮发送追加进同一条会话，事后在通用「Deepcoffee AI」里翻得到。
  useEffect(() => {
    if (!storageKey || restoredRef.current) return
    restoredRef.current = true
    if (isWizard) {
      setMessages([{ role: 'assistant', text: isBean ? BEAN_WIZARD_GUIDE : BREW_WIZARD_GUIDE, at: Date.now() }])
      getCoffeaSession(getToken())
        .then(server => { if (server) setSessionId(server.session_id) })
        .catch(() => {})
      return
    }
    let cancelled = false
    ;(async () => {
      const server = await getCoffeaSession(getToken())
      if (cancelled) return
      if (server) {
        setSessionId(server.session_id)
        if (server.turns.length > 0) {
          // 服务端是真相（跨设备）：文字 / 结果 / 图片 URL 都来自服务端。
          setMessages(server.turns.map(t => ({
            role: t.role,
            text: t.text ?? undefined,
            results: t.results,
            at: t.at ?? undefined,
            images: t.images ?? undefined,
          })))
        }
        return
      }
      // 服务端不可达：回退本地缓存
      try {
        const raw = localStorage.getItem(storageKey)
        if (!raw) return
        const saved = JSON.parse(raw) as { v?: number; sessionId?: string | null; turns?: ChatTurn[] }
        if (saved.v === CHAT_STORE_VERSION && Array.isArray(saved.turns) && saved.turns.length > 0) {
          setMessages(saved.turns)
          setSessionId(saved.sessionId ?? null)
        }
      } catch { /* 损坏数据直接忽略 */ }
    })()
    return () => { cancelled = true }
  }, [storageKey])

  // 每次消息变化落盘（本地缓存，离线用；服务端才是真相）
  useEffect(() => {
    if (!storageKey || !restoredRef.current) return
    if (messages.some(m => m.role === 'user')) persistTurns(storageKey, sessionId, messages)
  }, [messages, sessionId, storageKey])

  const hasUserTurn = messages.some(m => m.role === 'user')
  const hints = isBean ? BEAN_GUIDE_HINTS : isBrew ? BREW_HINTS : mockSuggestions

  useEffect(() => {
    msgsRef.current?.scrollTo({ top: msgsRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // 输入框随内容自动撑高：先归零再按 scrollHeight 设高（发送清空后自动缩回单行；到 max-h 后内部滚动）
  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${ta.scrollHeight}px`
  }, [input])

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return
    setPreparingImages(true)
    try {
      const urls = await Promise.all(Array.from(files).map(f => compressImage(f)))
      setPendingImages(cur => [...cur, ...urls])
    } finally {
      setPreparingImages(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function send(text?: string) {
    const t = (text ?? input).trim()
    if ((!t && pendingImages.length === 0) || sending || preparingImages) return
    const images = pendingImages
    const attachments: CoffeaAttachment[] = images.map(d => ({
      type: 'image',
      data_url: d,
      mime_type: dataUrlMime(d),
    }))

    setInput('')
    setPendingImages([])
    setSending(true)
    setMessages(cur => [
      ...cur,
      { role: 'user', text: t, images, at: Date.now() },
      { role: 'assistant', pending: true },
    ])

    const controller = new AbortController()
    abortRef.current = controller
    // 自动超时：网络卡住/请求丢失时别让界面永久转圈（区别于用户手动「停止」）。
    // 带图轮要走视觉模型（较慢），给足时间，避免后端其实成功了前端却先判超时。
    const timeout = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), 150_000)
    try {
      const res = await sendCoffeaMessage(
        { message: t, session_id: sessionId, attachments, ...(isBean ? { mode: 'bean_create' as const } : {}) },
        getToken(),
        controller.signal,
      )
      setSessionId(res.session_id)

      // reply 是后端组装好的主回复；results 只作为动作明细展示，不再由前端决定主气泡正文。
      const hasResultContent = res.results.some(
        r => r.message?.trim() || getSources(r.output).length > 0 || (r.output && Object.keys(r.output).length > 0),
      )
      let turn: ChatTurn = { role: 'assistant', text: res.reply, results: res.results, at: Date.now() }

      // 兜底：永远不要留空气泡
      if (!turn.text?.trim() && !(turn.results && turn.results.length > 0)) {
        turn = { ...turn, text: '已收到，但暂时没有更多内容可显示。' }
      }

      setMessages(cur => {
        const next = [...cur]
        next[next.length - 1] = turn
        return next
      })
    } catch (err) {
      // abort 分两种：自动超时 vs 用户手动「停止」。后端不支持中途取消，
      // 本次请求服务端仍会跑完并计入额度，停止/超时只是前端不再等待结果。
      if (controller.signal.aborted) {
        const timedOut = (controller.signal.reason as DOMException | undefined)?.name === 'TimeoutError'
        const text = timedOut
          ? '响应超时了，网络似乎不太稳定，请重试一下。'
          : '（已停止本次回复）'
        setMessages(cur => {
          const next = [...cur]
          next[next.length - 1] = { role: 'assistant', text, at: Date.now() }
          return next
        })
        return
      }
      const quota = isQuotaExceeded(err)
      const msg = err instanceof Error ? err.message : '请求失败，请稍后重试。'
      setMessages(cur => {
        const next = [...cur]
        next[next.length - 1] = { role: 'assistant', error: msg, quota, at: Date.now() }
        return next
      })
    } finally {
      clearTimeout(timeout)
      abortRef.current = null
      setSending(false)
    }
  }

  function stopSending() {
    abortRef.current?.abort()
  }

  // 草稿确认/忽略后把状态写回该轮 result.output（随消息一起持久化，刷新后不丢）
  async function patchResultOutput(msgIdx: number, resIdx: number, patch: Record<string, unknown>, message?: string) {
    const target = messages[msgIdx]?.results?.[resIdx]
    const uiStateId = typeof target?.output?.ui_state_id === 'string' ? target.output.ui_state_id : null
    setMessages(cur => cur.map((m, i) => {
      if (i !== msgIdx || !m.results) return m
      let nextText = m.text
      const results = m.results.map((r, j) => {
        if (j !== resIdx) return r
        if (message) {
          const oldMessage = r.message?.trim()
          if (oldMessage && nextText?.includes(oldMessage)) {
            nextText = nextText.replace(oldMessage, message)
          } else if (!nextText?.trim()) {
            nextText = message
          }
        }
        return {
          ...r,
          message: message ?? r.message,
          output: { ...(r.output ?? {}), ...patch },
        }
      })
      return { ...m, text: nextText, results }
    }))
    if (uiStateId) {
      try {
        await patchCoffeaSessionResult(uiStateId, patch, message, getToken())
      } catch (err) {
        console.warn('Failed to persist Coffea card state', err)
      }
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={msgsRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Empty hero */}
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center gap-6 text-center">
            <div>
              <div className="w-12 h-12 rounded-full bg-dc-accent-light flex items-center justify-center mx-auto mb-3 overflow-hidden border border-dc-border">
                <img src="/logo.png" alt="DeepCoffee" className="w-full h-full object-contain p-1" />
              </div>
              <h2 className="font-semibold text-dc-text-1 mb-1">Coffea</h2>
              <p className="text-sm text-dc-text-3">描述冲煮、上传豆袋照片，或问任何关于咖啡的问题</p>
            </div>
            <div className="w-full max-w-md space-y-2 text-left">
              <p className="text-xs text-dc-text-3 px-1">快速开始</p>
              {hints.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="w-full text-left text-sm text-dc-text-2 dc-card px-4 py-3 hover:border-dc-accent hover:text-dc-accent hover:bg-dc-accent-light transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message thread */}
        {messages.map((m, i) => {
          // 微信式居中时间戳：首条带时间的消息，或与上一条带时间消息间隔超过阈值
          let showTime = false
          if (m.at) {
            let prevAt: number | undefined
            for (let j = i - 1; j >= 0; j--) {
              if (messages[j].at) { prevAt = messages[j].at; break }
            }
            showTime = prevAt === undefined || m.at - prevAt > TIME_GAP_MS
          }
          const bubble = m.role === 'user' ? (
            <div className="flex gap-3 justify-end">
              <div className="space-y-2 max-w-lg">
                {m.images && m.images.length > 0 && (
                  <div className="flex flex-wrap gap-2 justify-end">
                    {m.images.map((src, j) => (
                      <button
                        key={j}
                        type="button"
                        onClick={() => setLightboxSrc(src)}
                        aria-label="查看大图"
                        className="block rounded-lg overflow-hidden border border-dc-border cursor-zoom-in hover:opacity-90 transition-opacity"
                      >
                        <img src={src} alt="附件" className="w-24 h-24 object-cover" />
                      </button>
                    ))}
                  </div>
                )}
                {m.text && (
                  <div className="bg-dc-accent text-white text-sm px-4 py-3 rounded-2xl rounded-br-sm whitespace-pre-wrap break-words">
                    {m.text}
                  </div>
                )}
              </div>
              <UserAvatar />
            </div>
          ) : (
            <div className="flex gap-3 items-start">
              <AiAvatar />
              {m.pending ? (
                <TypingDots />
              ) : m.quota ? (
                <QuotaNotice message={m.error} />
              ) : m.error ? (
                <div className="bg-red-50 border border-red-100 text-sm px-4 py-3 rounded-2xl rounded-tl-sm max-w-lg flex items-start gap-2">
                  <AlertTriangle size={14} className="text-dc-red flex-shrink-0 mt-0.5" />
                  <span className="text-dc-red">{m.error}</span>
                </div>
              ) : (
                <div className="space-y-3 max-w-lg w-full">
                  {m.text && (
                    <div className="bg-white border border-dc-border text-sm px-4 py-3 rounded-2xl rounded-tl-sm text-dc-text-1 leading-relaxed">
                      <ChatMarkdown text={m.text} />
                    </div>
                  )}
                  {m.results?.map((r, j) => {
                    if (r.type === 'read_bean_card_image' && r.output?.auto_saved && typeof r.output.bean_id === 'string') {
                      return <AutoSavedBeanCard key={j} beanId={r.output.bean_id} />
                    }
                    if (r.type === 'brew_record_offer') {
                      return <BrewRecordOffer key={j} result={r} onSend={(text) => send(text)} />
                    }
                    if ((r.type === 'read_bean_card_image' || r.type === 'create_or_update_bean_card') && r.output?.draft) {
                      return <ChatBeanDraft key={j} result={r} onPatch={(patch, message) => patchResultOutput(i, j, patch, message)} />
                    }
                    if (r.type === 'brew_record_parse' && r.output?.draft) {
                      return (
                        <ChatBrewDraft
                          key={j}
                          result={r}
                          linkedBeanId={linkedBeanId}
                          onPatch={(patch, message) => patchResultOutput(i, j, patch, message)}
                        />
                      )
                    }
                    if (r.type === 'equipment_capture' && r.output?.items) {
                      return <ChatEquipmentDraft key={j} result={r} onPatch={(patch, message) => patchResultOutput(i, j, patch, message)} />
                    }
                    return <ActionResultCard key={j} result={r} replyText={m.text} />
                  })}
                </div>
              )}
            </div>
          )
          return (
            <div key={i} className="space-y-6">
              {showTime && m.at && <TimeDivider at={m.at} />}
              {bubble}
            </div>
          )
        })}

        {/* Quick hints before first user message (brew seeded mode) */}
        {messages.length > 0 && !hasUserTurn && (
          <div className="flex gap-3 items-start">
            <div className="w-8 flex-shrink-0" />
            <div className="space-y-1.5 max-w-lg w-full">
              {hints.map(h => (
                <button
                  key={h}
                  onClick={() => send(h)}
                  className="block w-full text-left text-xs text-dc-text-3 bg-dc-subtle rounded-lg px-3 py-2 hover:bg-dc-accent-light hover:text-dc-accent transition-colors"
                >
                  {h}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="px-4 sm:px-6 py-4 border-t border-dc-border bg-dc-bg">
        {(pendingImages.length > 0 || preparingImages) && (
          <div className="flex flex-wrap gap-2 mb-3">
            {pendingImages.map((src, i) => (
              <div key={i} className="relative">
                <img src={src} alt="待发送" className="w-16 h-16 object-cover rounded-lg border border-dc-border" />
                <button
                  onClick={() => setPendingImages(cur => cur.filter((_, j) => j !== i))}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-dc-text-1 text-white flex items-center justify-center"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
            {preparingImages && (
              <div className="h-16 px-3 rounded-lg border border-dc-border bg-white flex items-center text-xs text-dc-text-3">
                图片处理中…
              </div>
            )}
          </div>
        )}
        <div className="flex gap-2 items-end w-full">
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={e => handleFiles(e.target.files)} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={sending || preparingImages}
            title="上传图片"
            className="text-dc-text-3 hover:text-dc-accent p-2.5 flex-shrink-0 disabled:opacity-40"
          >
            <ImagePlus size={18} />
          </button>
          <textarea
            ref={taRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={sending}
            rows={1}
            className="dc-input flex-1 resize-none max-h-28 overflow-y-auto leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder={sending ? 'Coffea 思考中…' : preparingImages ? '图片处理中…' : ''}
          />
          {sending ? (
            <button
              onClick={stopSending}
              title="停止"
              className="btn-primary p-2.5 flex-shrink-0"
            >
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={() => send()}
              disabled={preparingImages || (!input.trim() && pendingImages.length === 0)}
              className="btn-primary p-2.5 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// 建豆卡结构化流程（parse → 草稿确认 → confirm）
// ─────────────────────────────────────────────────────────
function DraftInput({
  label, value, lowConf, onChange, placeholder,
}: {
  label: string; value: string; lowConf?: boolean
  onChange: (value: string) => void; placeholder?: string
}) {
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={`dc-input text-sm ${lowConf ? 'border-dc-yellow bg-dc-yellow-bg/50' : ''}`}
      />
    </label>
  )
}

// 可搜索下拉 + 自由输入/新增（吃公共实体目录 ∪ 用户已有值），和表单 BeanForm 的 ComboField 一致；lowConf 复用 Combobox.highlight。
function DraftCombo({
  label, value, options, lowConf, placeholder, onInput, onSelect,
}: {
  label: string; value: string; options: ComboOption[]; lowConf?: boolean
  placeholder?: string; onInput: (value: string) => void; onSelect: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">{label}</span>
      <Combobox
        options={options}
        value={value}
        placeholder={placeholder ?? `输入或选择${label}`}
        highlight={lowConf}
        onInput={onInput}
        onSelect={onSelect}
      />
    </label>
  )
}

function BeanDraftCard({
  draft, confidence, lowConfidenceFields, clarification, error, saving, suggestions, onChange, onConfirm, onRetry,
  retryLabel = '重新描述',
}: {
  draft: BeanDraft | null
  confidence: number | null
  lowConfidenceFields: string[]
  clarification?: string | null
  error: string
  saving: boolean
  suggestions: BeanFieldSuggestions
  onChange: (draft: BeanDraft) => void
  onConfirm: () => void
  onRetry: () => void
  retryLabel?: string
}) {
  if (!draft) {
    return (
      <div className="dc-card p-4">
        <div className="flex items-start gap-2">
          <AlertTriangle size={14} className="text-dc-yellow flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-semibold text-dc-text-1 mb-1">豆卡识别失败</div>
            <p className="text-sm text-dc-text-3">{error || '请换一种描述方式再试一次。'}</p>
          </div>
        </div>
        <button onClick={onRetry} className="btn-secondary text-sm py-2 mt-4">重新描述</button>
      </div>
    )
  }

  const isLow = (field: string) => lowConfidenceFields.includes(field)
  const setField = <K extends keyof BeanDraft>(key: K, value: BeanDraft[K]) => {
    onChange({ ...draft, [key]: value })
  }
  const components = draft.bean_components?.length ? draft.bean_components : []
  const writeComponents = (next: BeanComponent[]) => onChange({ ...draft, bean_components: next })
  const setComponent = (index: number, patch: Partial<BeanComponent>) => {
    writeComponents(components.map((component, i) => i === index ? { ...component, ...patch } : component))
  }
  const addComponent = () => writeComponents([
    ...components,
    {
      origin_name: '', coffee_source_name: '', green_bean_merchant_name: '', green_bean_product_name: '',
      process_name: '', varietal_names: [], altitude_text: '', harvest_date_text: '', share_text: '',
    },
  ])
  const removeComponent = (index: number) => writeComponents(components.filter((_, i) => i !== index))
  const activeComponents = components.filter(beanComponentHasContent)
  const canSave = Boolean(
    (draft.name?.trim() || draft.roaster_product_name?.trim())
    && draft.roaster_name?.trim()
    && activeComponents.length > 0
    && activeComponents.every(component => component.origin_name?.trim() && component.process_name?.trim()),
  )

  return (
    <div className="dc-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dc-border">
        <span className="text-sm font-semibold text-dc-text-1">豆卡草稿</span>
        {confidence !== null && (
          <span className="text-xs bg-dc-green-bg text-dc-green px-2 py-0.5 rounded-full font-medium">
            识别度 {Math.round(confidence * 100)}%
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        <DraftInput
          label="豆卡名称"
          value={draft.name ?? ''}
          lowConf={isLow('name')}
          onChange={(value) => setField('name', value)}
          placeholder="例如：翡翠庄园 瑰夏 水洗"
        />
        <div className="grid sm:grid-cols-2 gap-3">
          <DraftCombo label="烘焙商" value={draft.roaster_name ?? ''} options={suggestions.roasters} lowConf={isLow('roaster_name')} onInput={(value) => setField('roaster_name', value)} onSelect={(value) => setField('roaster_name', value)} />
          <DraftInput label="烘焙商产品 / 批次名" value={draft.roaster_product_name ?? ''} lowConf={isLow('roaster_product_name')} onChange={(value) => setField('roaster_product_name', value)} />
          <DraftInput label="烘焙日期" value={draft.roast_date_text ?? ''} lowConf={isLow('roast_date_text')} onChange={(value) => setField('roast_date_text', value)} />
          <DraftInput label="净含量" value={draft.net_weight_text ?? ''} lowConf={isLow('net_weight_text')} onChange={(value) => setField('net_weight_text', value)} />
        </div>
        <div className="border-t border-dc-border pt-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-dc-text-2">豆源（单豆填 1 条，拼配可加多条）</span>
            <button type="button" onClick={addComponent} className="text-xs text-dc-accent inline-flex items-center gap-1">
              <Plus size={12} />
              添加豆源
            </button>
          </div>
          {components.length === 0 ? (
            <p className="text-xs text-dc-text-3">点「添加豆源」填写产地、处理法、品种等信息。</p>
          ) : (
            <div className="space-y-3">
              {components.map((component, index) => (
                <div key={index} className="border border-dc-border rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-dc-text-1">豆源 {index + 1}</span>
                    {components.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeComponent(index)}
                        className="text-dc-red hover:bg-dc-red/5 rounded-md p-1"
                        aria-label="删除豆源"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                  <div className="grid sm:grid-cols-2 gap-2">
                    <DraftCombo label="产地" value={component.origin_name ?? ''} options={suggestions.origins} onInput={(value) => setComponent(index, { origin_name: value })} onSelect={(value) => setComponent(index, { origin_name: value })} />
                    <DraftInput label="生产者/庄园/处理站" value={component.coffee_source_name ?? ''} onChange={(value) => setComponent(index, { coffee_source_name: value })} />
                    <DraftCombo label="处理法" value={component.process_name ?? ''} options={suggestions.processes} onInput={(value) => setComponent(index, { process_name: value })} onSelect={(value) => setComponent(index, { process_name: value })} />
                    <DraftCombo
                      label="品种"
                      value={(component.varietal_names ?? []).join('，')}
                      options={suggestions.varietals}
                      placeholder="输入或选择品种，多个用逗号分隔"
                      onInput={(value) => setComponent(index, { varietal_names: value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })}
                      onSelect={(value) => {
                        const cur = component.varietal_names ?? []
                        if (!cur.includes(value)) setComponent(index, { varietal_names: [...cur, value] })
                      }}
                    />
                    <DraftInput label="生豆商/进口商" value={component.green_bean_merchant_name ?? ''} onChange={(value) => setComponent(index, { green_bean_merchant_name: value })} />
                    <DraftInput label="生豆商产品" value={component.green_bean_product_name ?? ''} onChange={(value) => setComponent(index, { green_bean_product_name: value })} />
                    <DraftInput label="海拔" value={component.altitude_text ?? ''} onChange={(value) => setComponent(index, { altitude_text: value })} />
                    <DraftInput label="采收期" value={component.harvest_date_text ?? ''} onChange={(value) => setComponent(index, { harvest_date_text: value })} />
                    <DraftInput label="占比/说明" value={component.share_text ?? ''} onChange={(value) => setComponent(index, { share_text: value })} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <label className="block">
          <span className="text-xs text-dc-text-3 mb-1 block">备注</span>
          <textarea
            value={draft.private_notes ?? ''}
            onChange={(event) => setField('private_notes', event.target.value)}
            className="dc-input text-sm min-h-[72px] resize-none leading-relaxed"
          />
        </label>
      </div>

      {(clarification || error || lowConfidenceFields.length > 0) && (
        <div className="px-4 py-2.5 bg-dc-yellow-bg border-t border-yellow-100 flex items-center gap-2">
          <AlertTriangle size={12} className="text-dc-yellow flex-shrink-0" />
          <span className="text-xs text-dc-yellow">{error || clarification || '黄色字段建议确认后再保存'}</span>
        </div>
      )}

      <div className="px-4 py-3 border-t border-dc-border flex gap-2">
        <button
          onClick={onConfirm}
          disabled={saving || !canSave}
          className="btn-primary text-sm py-2 flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '保存中…' : '确认保存'}
        </button>
        <button onClick={onRetry} className="btn-secondary text-sm py-2">{retryLabel}</button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
function ChatInner() {
  const searchParams = useSearchParams()
  const newMode = searchParams.get('new')        // '1' = 冲煮记录向导, 'bean' = 建豆卡向导, null = 通用会话
  const linkedBeanId = searchParams.get('bean_id')

  return <CoffeaChat newMode={newMode} linkedBeanId={linkedBeanId} />
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatInner />
    </Suspense>
  )
}
