'use client'
import { useState, useRef, useEffect, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  Send, AlertTriangle, AlertCircle, CheckCircle2, Clock, RotateCcw,
  ImagePlus, X, Globe, Square,
} from 'lucide-react'
import { confirmBean, getBeans, parseBeanInput } from '@/lib/api/beans'
import { listEquipment, type EquipmentProfile } from '@/lib/api/equipment'
import { confirmBrew } from '@/lib/api/records'
import { sendCoffeaMessage, fileToDataUrl, mockSuggestions } from '@/lib/api/chat'
import { isQuotaExceeded } from '@/lib/api/client'
import { QuotaNotice } from '@/components/QuotaNotice'
import { ChatMarkdown } from '@/components/ChatMarkdown'
import { useProfile } from '@/components/ProfileContext'
import { getToken } from '@/lib/auth'
import type {
  Bean, BeanDraft, ActionResult, ActionStatus, CoffeaAttachment, WebVerifySource,
} from '@/types'

const BREW_HINTS = [
  '今天用 V60 冲了翡翠庄园瑰夏，15g 粉，225ml，93°C，2:40，甜感很好',
  'C40 #18，千峰庄园帕卡马拉 CM 日晒，15g，225ml，1:15，92°C',
]

const BEAN_GUIDE_HINTS = [
  '新入手：光合烘焙翡翠庄园瑰夏，水洗处理，巴拿马，还没开袋',
  '刚拿到千峰庄园帕卡马拉 CM 日晒，想先建个档案',
]

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

function ActionResultCard({ result, replyText }: { result: ActionResult; replyText?: string | null }) {
  const meta = statusMeta(result.status)
  const { Icon } = meta
  // 动作名只显示中文标签；未知类型一律「处理结果」，绝不裸显内部英文动作名
  const label = ACTION_LABEL[result.type] ?? '处理结果'
  const sources = getSources(result.output)
  // message 已被组装进顶层 reply 时不在卡片里重复；原始 output JSON 不再展示给用户
  const message = result.message?.trim()
  const duplicateOfReply = !!message && replyText?.trim() === message
  const showMessage = !!message && !duplicateOfReply
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
            {sources.map((s, i) => (
              <a
                key={i}
                href={s.url ?? '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-lg border border-dc-border px-2.5 py-1.5 hover:border-dc-accent-hi transition-colors"
              >
                <div className="text-dc-text-1 font-medium line-clamp-1">{s.title ?? s.url}</div>
                <div className="text-xs text-dc-text-3 line-clamp-1">
                  {s.url}{(s.published_at ?? s.time) ? ` · ${s.published_at ?? s.time}` : ''}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 聊天内豆卡草稿确认（read_bean_card_image 低识别度路径）──
function ChatBeanDraft({
  result,
  onPatch,
}: {
  result: ActionResult
  onPatch: (patch: Record<string, unknown>) => void
}) {
  const output = result.output ?? {}
  const savedBeanId = typeof output.saved_bean_id === 'string' ? output.saved_bean_id : null
  const [draft, setDraft] = useState<BeanDraft>(() => (output.draft as BeanDraft) ?? {})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  if (output.dismissed === true) return null
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
      const res = await confirmBean(draft, rawInput, getToken(), 'image')
      onPatch({ saved_bean_id: res.bean_id })
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
      onChange={setDraft}
      onConfirm={confirm}
      onRetry={() => onPatch({ dismissed: true })}
      retryLabel="忽略"
    />
  )
}

// ── 聊天内冲煮草稿确认（brew_record_parse 解析出参数后）──
const BREW_TEXT_FIELDS: { key: string; label: string; placeholder: string }[] = [
  { key: 'grind_setting', label: '研磨刻度', placeholder: '例如：4.8 圈' },
  { key: 'dose_g', label: '粉量 (g)', placeholder: '15' },
  { key: 'water_ml', label: '水量 (ml)', placeholder: '270' },
  { key: 'water_temp_c', label: '水温 (°C)', placeholder: '96' },
  { key: 'ratio', label: '粉水比', placeholder: '1:18' },
  { key: 'time', label: '时间', placeholder: '2:30 或 150（秒）' },
]

const CUSTOM = '__custom__'

// 下拉（来源：豆仓 / 我的器具）+「自定义输入」的组合字段
function ComboField({
  label, missing, options, choice, custom, placeholder, onChoice, onCustom,
}: {
  label: string
  missing: boolean
  options: { value: string; label: string }[]
  choice: string
  custom: string
  placeholder: string
  onChoice: (v: string) => void
  onCustom: (v: string) => void
}) {
  const empty = choice === '' || (choice === CUSTOM && !custom.trim())
  const highlight = missing && empty
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">
        {label}{highlight && <span className="text-dc-yellow ml-1">待补充</span>}
      </span>
      <select
        value={choice}
        onChange={e => onChoice(e.target.value)}
        className={`dc-input text-sm py-1.5 ${highlight ? 'border-dc-yellow bg-dc-yellow-bg/50' : ''}`}
      >
        <option value="">未选择</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        <option value={CUSTOM}>自定义输入…</option>
      </select>
      {choice === CUSTOM && (
        <input
          value={custom}
          onChange={e => onCustom(e.target.value)}
          placeholder={placeholder}
          className={`dc-input text-sm py-1.5 mt-1.5 ${highlight ? 'border-dc-yellow bg-dc-yellow-bg/50' : ''}`}
        />
      )}
    </label>
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
  onPatch: (patch: Record<string, unknown>) => void
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
  const parsedDevice = String(baseDraft.device ?? '').trim()
  const parsedGrinder = String(baseDraft.grinder ?? '').trim()

  // 下拉数据源：豆仓 + 我的器具；拉取失败回退为纯手输（空选项 + 自定义）
  const [beans, setBeans] = useState<Bean[] | null>(null)
  const [equipment, setEquipment] = useState<EquipmentProfile[] | null>(null)
  const [beanChoice, setBeanChoice] = useState(parsedBeanName ? CUSTOM : '')
  const [beanCustom, setBeanCustom] = useState(parsedBeanName)
  const [createBeanCard, setCreateBeanCard] = useState(true)
  const [device, setDevice] = useState({ choice: parsedDevice ? CUSTOM : '', custom: parsedDevice })
  const [grinder, setGrinder] = useState({ choice: parsedGrinder ? CUSTOM : '', custom: parsedGrinder })
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
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const beanInitRef = useRef(false)
  const equipInitRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    getBeans({}, getToken())
      .then(list => { if (!cancelled) setBeans(list) })
      .catch(() => { if (!cancelled) setBeans([]) })
    listEquipment()
      .then(list => { if (!cancelled) setEquipment(list) })
      .catch(() => { if (!cancelled) setEquipment([]) })
    return () => { cancelled = true }
  }, [])

  // 豆仓就绪后预选：来自豆卡页的 linkedBeanId 优先；其次解析名精确同名；未命中保持自定义预填
  useEffect(() => {
    if (beans === null || beanInitRef.current) return
    beanInitRef.current = true
    if (linkedBeanId && beans.some(b => b.bean_id === linkedBeanId)) {
      setBeanChoice(linkedBeanId)
      return
    }
    const match = parsedBeanName ? beans.find(b => b.name.trim() === parsedBeanName) : undefined
    if (match) setBeanChoice(match.bean_id)
  }, [beans, linkedBeanId, parsedBeanName])

  // 器具就绪后预选：解析值命中选项即选中；解析为空时取默认器具套
  useEffect(() => {
    if (equipment === null || equipInitRef.current) return
    equipInitRef.current = true
    const brewMethods = equipment.map(e => e.brew_method).filter(Boolean) as string[]
    const grinders = equipment.map(e => e.grinder).filter(Boolean) as string[]
    const def = equipment.find(e => e.is_default)
    setDevice(cur => {
      if (parsedDevice && brewMethods.includes(parsedDevice)) return { choice: parsedDevice, custom: '' }
      if (!parsedDevice && def?.brew_method) return { choice: def.brew_method, custom: '' }
      return cur
    })
    setGrinder(cur => {
      if (parsedGrinder && grinders.includes(parsedGrinder)) return { choice: parsedGrinder, custom: '' }
      if (!parsedGrinder && def?.grinder) return { choice: def.grinder, custom: '' }
      return cur
    })
  }, [equipment, parsedDevice, parsedGrinder])

  if (output.dismissed === true) return null
  if (savedRecordId) {
    return (
      <div className="dc-card px-4 py-3 text-sm space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-dc-green">
            <CheckCircle2 size={14} /> 已保存到冲煮记录
          </span>
          <Link href="/app/records" className="text-dc-accent hover:underline text-xs">
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
  const deviceOptions = uniq((equipment ?? []).map(e => e.brew_method)).map(v => ({ value: v, label: v }))
  const grinderOptions = uniq((equipment ?? []).map(e => e.grinder)).map(v => ({ value: v, label: v }))

  // 手输豆名且豆仓里没有同名豆 → 显示「顺手建豆卡」勾选
  const customBeanName = beanChoice === CUSTOM ? beanCustom.trim() : ''
  const customUnmatched = !!customBeanName && !(beans ?? []).some(b => b.name.trim() === customBeanName)

  async function confirm() {
    setSaving(true)
    setError('')
    try {
      const token = getToken()
      const rawInput = typeof output.raw_input === 'string' ? output.raw_input : undefined

      // 1) 解析豆子选择 → bean_card_id（下拉直选 / 同名匹配 / 勾选建档）
      let beanCardId: string | undefined
      let beanName: string | undefined
      let createdBeanId: string | undefined
      if (beanChoice && beanChoice !== CUSTOM) {
        beanCardId = beanChoice
        beanName = (beans ?? []).find(b => b.bean_id === beanChoice)?.name
      } else if (customBeanName) {
        beanName = customBeanName
        const match = (beans ?? []).find(b => b.name.trim() === customBeanName)
        if (match) {
          beanCardId = match.bean_id
        } else if (createBeanCard) {
          const created = await confirmBean({ name: customBeanName }, rawInput, token)
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
      // 2) 在解析草稿基础上合并用户编辑（注水步骤等其余字段原样保留）
      const merged: Record<string, unknown> = {
        ...baseDraft,
        bean_name: beanName,
        device: deviceValue || undefined,
        grinder: grinderValue || undefined,
        grind_setting: fields.grind_setting.trim() || undefined,
        dose_g: numeric(fields.dose_g),
        water_ml: numeric(fields.water_ml),
        water_temp_c: numeric(fields.water_temp_c),
        ratio: fields.ratio.trim() || undefined,
        brew_time_seconds: parseBrewTimeText(fields.time),
      }
      const res = await confirmBrew(merged, rawInput, beanCardId, token)
      onPatch({
        saved_record_id: res.brew_id,
        saved_recap: res.recap,
        ...(createdBeanId ? { saved_bean_id: createdBeanId, saved_bean_name: beanName } : {}),
      })
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
            onChoice={setBeanChoice}
            onCustom={setBeanCustom}
          />
          {customUnmatched && (
            <label className="flex items-center gap-1.5 mt-1.5 text-xs text-dc-text-2 cursor-pointer">
              <input
                type="checkbox"
                checked={createBeanCard}
                onChange={e => setCreateBeanCard(e.target.checked)}
                className="accent-dc-accent"
              />
              同时为这支豆建一张豆卡
            </label>
          )}
        </div>
        <ComboField
          label="滤杯"
          missing={missing.includes('device')}
          options={deviceOptions}
          choice={device.choice}
          custom={device.custom}
          placeholder="例如：V60"
          onChoice={v => setDevice({ choice: v, custom: device.custom })}
          onCustom={v => setDevice({ choice: device.choice, custom: v })}
        />
        <ComboField
          label="磨豆机"
          missing={missing.includes('grinder')}
          options={grinderOptions}
          choice={grinder.choice}
          custom={grinder.custom}
          placeholder="例如：ZP6S"
          onChoice={v => setGrinder({ choice: v, custom: grinder.custom })}
          onCustom={v => setGrinder({ choice: grinder.choice, custom: v })}
        />
        {BREW_TEXT_FIELDS.map(({ key, label, placeholder }) => {
          const isMissing = (key === 'time' ? missing.includes('brew_time_seconds') : missing.includes(key))
            && !fields[key].trim()
          return (
            <label key={key} className="block">
              <span className="text-xs text-dc-text-3 mb-1 block">
                {label}{isMissing && <span className="text-dc-yellow ml-1">待补充</span>}
              </span>
              <input
                value={fields[key]}
                onChange={e => setFields(cur => ({ ...cur, [key]: e.target.value }))}
                placeholder={placeholder}
                className={`dc-input text-sm py-1.5 ${isMissing ? 'border-dc-yellow bg-dc-yellow-bg/50' : ''}`}
              />
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
          disabled={saving}
          className="btn-primary text-sm py-2 flex-1 disabled:opacity-50"
        >
          {saving ? '保存中…' : '确认保存'}
        </button>
        <button onClick={() => onPatch({ dismissed: true })} className="btn-secondary text-sm py-2">忽略</button>
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

// 历史会话持久化：按用户 id 各存一份（localStorage，本机）。
// 图片 data URL 体积大，持久化时剥离；pending 中间态不落盘。
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
  const isBrew = newMode === '1'
  const { profile } = useProfile()
  const [messages, setMessages] = useState<ChatTurn[]>(() =>
    isBrew
      ? [{
          role: 'assistant',
          text: linkedBeanId
            ? '好的，来记录这次冲煮 ☕ 这条记录会关联到当前豆卡。直接用自然语言描述即可，细节越多识别越准。'
            : '好的，来记录这次冲煮 ☕ 直接描述器具、粉量、水量、水温、时间和风味即可，越详细识别越准。',
        }]
      : []
  )
  const [input, setInput] = useState('')
  const [pendingImages, setPendingImages] = useState<string[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const msgsRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  // restoredRef 置 true 后才开始写盘，避免「先用空数组覆盖了已存的历史」
  const restoredRef = useRef(false)

  const storageKey = profile ? chatStorageKey(profile.id) : null

  // 恢复历史（仅默认线程；?new=1 的冲煮引导按新对话处理，但后续仍会写盘）
  useEffect(() => {
    if (!storageKey || restoredRef.current) return
    restoredRef.current = true
    if (isBrew) return
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return
      const saved = JSON.parse(raw) as { v?: number; sessionId?: string | null; turns?: ChatTurn[] }
      if (saved.v === CHAT_STORE_VERSION && Array.isArray(saved.turns) && saved.turns.length > 0) {
        setMessages(saved.turns)
        setSessionId(saved.sessionId ?? null)
      }
    } catch { /* 损坏数据直接忽略 */ }
  }, [storageKey, isBrew])

  // 每次消息变化落盘
  useEffect(() => {
    if (!storageKey || !restoredRef.current) return
    if (messages.some(m => m.role === 'user')) persistTurns(storageKey, sessionId, messages)
  }, [messages, sessionId, storageKey])

  const hasUserTurn = messages.some(m => m.role === 'user')
  const hints = isBrew ? BREW_HINTS : mockSuggestions

  useEffect(() => {
    msgsRef.current?.scrollTo({ top: msgsRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return
    const urls = await Promise.all(Array.from(files).map(fileToDataUrl))
    setPendingImages(cur => [...cur, ...urls])
    if (fileRef.current) fileRef.current.value = ''
  }

  async function send(text?: string) {
    const t = (text ?? input).trim()
    if ((!t && pendingImages.length === 0) || sending) return
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
    try {
      const res = await sendCoffeaMessage(
        { message: t, session_id: sessionId, attachments },
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
      // 用户主动停止：不算错误，气泡改为「已停止」。注意后端不支持中途取消，
      // 本次请求服务端仍会跑完并计入额度，停止只是前端不再等待结果。
      if (controller.signal.aborted) {
        setMessages(cur => {
          const next = [...cur]
          next[next.length - 1] = { role: 'assistant', text: '（已停止本次回复）', at: Date.now() }
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
      abortRef.current = null
      setSending(false)
    }
  }

  function stopSending() {
    abortRef.current?.abort()
  }

  // 草稿确认/忽略后把状态写回该轮 result.output（随消息一起持久化，刷新后不丢）
  function patchResultOutput(msgIdx: number, resIdx: number, patch: Record<string, unknown>) {
    setMessages(cur => cur.map((m, i) => {
      if (i !== msgIdx || !m.results) return m
      const results = m.results.map((r, j) =>
        j === resIdx ? { ...r, output: { ...(r.output ?? {}), ...patch } } : r,
      )
      return { ...m, results }
    }))
  }

  function resetThread() {
    setMessages([])
    setSessionId(null)
    setPendingImages([])
    setInput('')
    if (storageKey) localStorage.removeItem(storageKey)
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
                      <img key={j} src={src} alt="附件" className="w-24 h-24 object-cover rounded-lg border border-dc-border" />
                    ))}
                  </div>
                )}
                {m.text && (
                  <div className="bg-dc-accent text-white text-sm px-4 py-3 rounded-2xl rounded-br-sm">
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
                    if (r.type === 'read_bean_card_image' && r.output?.draft) {
                      return <ChatBeanDraft key={j} result={r} onPatch={(patch) => patchResultOutput(i, j, patch)} />
                    }
                    if (r.type === 'brew_record_parse' && r.output?.draft) {
                      return (
                        <ChatBrewDraft
                          key={j}
                          result={r}
                          linkedBeanId={linkedBeanId}
                          onPatch={(patch) => patchResultOutput(i, j, patch)}
                        />
                      )
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
        {pendingImages.length > 0 && (
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
          </div>
        )}
        <div className="flex gap-2 items-end w-full">
          {hasUserTurn && (
            <button
              onClick={resetThread}
              title="新对话"
              className="text-dc-text-3 hover:text-dc-text-2 p-2.5 flex-shrink-0"
            >
              <RotateCcw size={16} />
            </button>
          )}
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={e => handleFiles(e.target.files)} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={sending}
            title="上传图片"
            className="text-dc-text-3 hover:text-dc-accent p-2.5 flex-shrink-0 disabled:opacity-40"
          >
            <ImagePlus size={18} />
          </button>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={sending}
            rows={1}
            className="dc-input flex-1 resize-none max-h-28 leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder={sending ? 'Coffea 思考中…' : isBrew ? '描述这次冲煮，例如：今天用 V60 冲了瑰夏…' : '描述冲煮，或随便问…'}
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
              disabled={!input.trim() && pendingImages.length === 0}
              className="btn-primary p-2.5 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
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

function BeanDraftCard({
  draft, confidence, lowConfidenceFields, clarification, error, saving, onChange, onConfirm, onRetry,
  retryLabel = '重新描述',
}: {
  draft: BeanDraft | null
  confidence: number | null
  lowConfidenceFields: string[]
  clarification?: string | null
  error: string
  saving: boolean
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
          <DraftInput label="烘焙商" value={draft.roaster_name ?? ''} lowConf={isLow('roaster_name')} onChange={(value) => setField('roaster_name', value)} />
          <DraftInput label="烘焙商产品" value={draft.roaster_product_name ?? ''} lowConf={isLow('roaster_product_name')} onChange={(value) => setField('roaster_product_name', value)} />
          <DraftInput label="生产者/庄园/处理站" value={draft.coffee_source_name ?? ''} lowConf={isLow('coffee_source_name')} onChange={(value) => setField('coffee_source_name', value)} />
          <DraftInput label="生豆商/进口商" value={draft.green_bean_merchant_name ?? ''} lowConf={isLow('green_bean_merchant_name')} onChange={(value) => setField('green_bean_merchant_name', value)} />
          <DraftInput label="生豆商产品" value={draft.green_bean_product_name ?? ''} lowConf={isLow('green_bean_product_name')} onChange={(value) => setField('green_bean_product_name', value)} />
          <DraftInput label="产地" value={draft.origin_name ?? ''} lowConf={isLow('origin_name')} onChange={(value) => setField('origin_name', value)} />
          <DraftInput label="处理法" value={draft.process_name ?? ''} lowConf={isLow('process_name')} onChange={(value) => setField('process_name', value)} />
          <DraftInput
            label="品种"
            value={(draft.varietal_names ?? []).join('，')}
            lowConf={isLow('varietal_names')}
            onChange={(value) => setField('varietal_names', value.split(/[，,]/).map((item) => item.trim()).filter(Boolean))}
          />
        </div>
        <label className="block">
          <span className="text-xs text-dc-text-3 mb-1 block">私有备注</span>
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
          disabled={saving || !draft.name?.trim()}
          className="btn-primary text-sm py-2 flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '保存中…' : '确认保存'}
        </button>
        <button onClick={onRetry} className="btn-secondary text-sm py-2">{retryLabel}</button>
      </div>
    </div>
  )
}

type BeanFlow = 'guide' | 'typing' | 'beanDraft' | 'saved'

function BeanCreateChat() {
  const [flow, setFlow] = useState<BeanFlow>('guide')
  const [input, setInput] = useState('')
  const [lastUserText, setLastUserText] = useState('')
  const [beanDraft, setBeanDraft] = useState<BeanDraft | null>(null)
  const [beanConfidence, setBeanConfidence] = useState<number | null>(null)
  const [beanLowConfidence, setBeanLowConfidence] = useState<string[]>([])
  const [beanClarification, setBeanClarification] = useState<string | null>(null)
  const [beanRawInput, setBeanRawInput] = useState('')
  const [beanError, setBeanError] = useState('')
  const [beanQuota, setBeanQuota] = useState('')   // 402 ai_quota_exceeded 消息
  const [savedBeanId, setSavedBeanId] = useState('')
  const [savingBean, setSavingBean] = useState(false)
  const msgsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    msgsRef.current?.scrollTo({ top: msgsRef.current.scrollHeight, behavior: 'smooth' })
  }, [flow])

  async function send(text?: string) {
    const t = (text ?? input).trim()
    if (!t) return
    setInput('')
    setLastUserText(t)
    setFlow('typing')
    setBeanRawInput(t)
    setBeanDraft(null)
    setBeanError('')
    setBeanQuota('')
    setBeanClarification(null)
    try {
      const res = await parseBeanInput(t, getToken())
      setBeanDraft(res.draft)
      setBeanConfidence(res.confidence)
      setBeanLowConfidence(res.low_confidence_fields)
      setBeanClarification(res.clarification ?? null)
    } catch (err) {
      if (isQuotaExceeded(err)) {
        setBeanQuota(err.message)
      } else {
        setBeanError(err instanceof Error ? err.message : '豆卡识别失败，请稍后重试。')
      }
    } finally {
      setFlow('beanDraft')
    }
  }

  async function confirmBeanDraft() {
    if (!beanDraft || savingBean) return
    setSavingBean(true)
    setBeanError('')
    try {
      const res = await confirmBean(beanDraft, beanRawInput, getToken())
      setSavedBeanId(res.bean_id)
      setFlow('saved')
    } catch (err) {
      setBeanError(err instanceof Error ? err.message : '豆卡保存失败，请稍后重试。')
    } finally {
      setSavingBean(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={msgsRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Guide */}
        {flow === 'guide' && (
          <div className="flex gap-3 items-start">
            <AiAvatar />
            <div className="space-y-3 max-w-lg w-full">
              <div className="bg-white border border-dc-border text-sm px-4 py-3 rounded-2xl rounded-tl-sm text-dc-text-1 leading-relaxed space-y-2">
                <p>好的，我来帮你建立豆卡 🫘</p>
                <p className="text-dc-text-2">告诉我豆子的基本信息——烘焙商、豆名、产区、处理法、品种，想附上购入渠道和价格也可以：</p>
                <div className="mt-1 space-y-1.5">
                  {BEAN_GUIDE_HINTS.map(h => (
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
            </div>
          </div>
        )}

        {(flow === 'typing' || flow === 'beanDraft' || flow === 'saved') && (
          <div className="space-y-6">
            {/* User message */}
            <div className="flex gap-3 justify-end">
              <div className="bg-dc-accent text-white text-sm px-4 py-3 rounded-2xl rounded-br-sm max-w-lg">
                {lastUserText}
              </div>
              <UserAvatar />
            </div>

            {flow === 'typing' && (
              <div className="flex gap-3 items-end">
                <AiAvatar />
                <TypingDots />
              </div>
            )}

            {flow === 'beanDraft' && beanQuota && (
              <div className="flex gap-3 items-start">
                <AiAvatar />
                <QuotaNotice message={beanQuota} />
              </div>
            )}

            {flow === 'beanDraft' && !beanQuota && (
              <div className="flex gap-3 items-start">
                <AiAvatar />
                <div className="space-y-3 max-w-2xl w-full">
                  <div className="bg-white border border-dc-border text-sm px-4 py-2.5 rounded-2xl rounded-tl-sm text-dc-text-1">
                    我把这段信息整理成了豆卡草稿，请确认后保存：
                  </div>
                  <BeanDraftCard
                    draft={beanDraft}
                    confidence={beanConfidence}
                    lowConfidenceFields={beanLowConfidence}
                    clarification={beanClarification}
                    error={beanError}
                    saving={savingBean}
                    onChange={setBeanDraft}
                    onConfirm={confirmBeanDraft}
                    onRetry={() => setFlow('guide')}
                  />
                </div>
              </div>
            )}

            {flow === 'saved' && (
              <div className="flex gap-3 items-start">
                <AiAvatar />
                <div className="space-y-3 max-w-lg w-full">
                  <div className="flex items-center gap-2 text-dc-green text-sm font-medium">
                    <CheckCircle2 size={15} />
                    已保存到你的豆仓
                  </div>
                  <div className="bg-white border border-dc-border text-sm px-4 py-3 rounded-2xl rounded-tl-sm text-dc-text-1 leading-relaxed">
                    豆卡已经建立。后续冲煮记录可以关联到这张豆卡，公共实体候选也会进入后台审核流程。
                  </div>
                  <div className="flex gap-2">
                    <Link
                      href={savedBeanId ? `/app/beans/${savedBeanId}` : '/app/beans'}
                      className="btn-primary text-sm py-2 px-4"
                    >
                      查看豆卡
                    </Link>
                    <Link href="/app/beans" className="btn-secondary text-sm py-2 px-4">返回豆仓</Link>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="px-4 sm:px-6 py-4 border-t border-dc-border bg-dc-bg">
        <div className="flex gap-3 items-end w-full">
          {flow === 'saved' && (
            <button onClick={() => setFlow('guide')} className="text-dc-text-3 hover:text-dc-text-2 p-2.5 flex-shrink-0">
              <RotateCcw size={16} />
            </button>
          )}
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={flow === 'typing'}
            rows={1}
            className="dc-input flex-1 resize-none max-h-28 leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder={
              flow === 'typing' ? 'AI 整理中…' :
              flow === 'beanDraft' ? '有修改？可以直接在草稿里调整…' :
              flow === 'saved' ? '继续建下一张豆卡…' :
              '描述豆子，例如：光合烘焙翡翠庄园瑰夏…'
            }
          />
          <button
            onClick={() => send()}
            disabled={flow === 'typing' || (!input.trim() && flow !== 'guide')}
            className="btn-primary p-2.5 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
function ChatInner() {
  const searchParams = useSearchParams()
  const newMode = searchParams.get('new')        // '1' = 冲煮记录, 'bean' = 建豆卡
  const linkedBeanId = searchParams.get('bean_id')

  if (newMode === 'bean') return <BeanCreateChat />
  return <CoffeaChat newMode={newMode} linkedBeanId={linkedBeanId} />
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatInner />
    </Suspense>
  )
}
