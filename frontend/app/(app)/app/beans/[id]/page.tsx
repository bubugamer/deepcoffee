'use client'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'next/navigation'
import { ArrowLeft, ClipboardList, Loader2, MessageSquare, Pencil, Plus, Trash2 } from 'lucide-react'
import { getBean, updateBean, setManualRecommendParams, type BeanUpdateInput, type ManualRecommendParams } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { formatBrewSeconds, recommendedParamRows } from '@/lib/beans'
import { RecommendParamsChat } from '@/components/RecommendParamsChat'
import type { Bean, BeanComponent, BeanDraft, BrewEvaluation, BrewEvaluationItem, FlavorAxis } from '@/types'

const FIELD_DEFS: { draftKey: keyof BeanDraft & string; beanKey: keyof Bean & string; label: string; required?: boolean }[] = [
  { draftKey: 'roaster_name', beanKey: 'roaster', label: '烘焙商', required: true },
  { draftKey: 'roaster_product_name', beanKey: 'roaster_product', label: '烘焙商产品 / 批次名' },
  { draftKey: 'coffee_source_name', beanKey: 'coffee_source', label: '生产者 / 庄园 / 处理站' },
  { draftKey: 'green_bean_merchant_name', beanKey: 'green_bean_merchant', label: '生豆商 / 进口商' },
  { draftKey: 'green_bean_product_name', beanKey: 'green_bean_product', label: '生豆商产品' },
  { draftKey: 'origin_name', beanKey: 'origin', label: '产地', required: true },
  { draftKey: 'process_name', beanKey: 'process', label: '处理法', required: true },
  { draftKey: 'altitude_text', beanKey: 'altitude_text', label: '海拔' },
  { draftKey: 'harvest_date_text', beanKey: 'harvest_date_text', label: '采收期' },
  { draftKey: 'roast_date_text', beanKey: 'roast_date_text', label: '烘焙日期' },
  { draftKey: 'net_weight_text', beanKey: 'net_weight_text', label: '净含量' },
]

const RATING_FIELDS: { key: keyof BrewEvaluation; label: string }[] = [
  { key: 'overall', label: '总评' },
  { key: 'aroma', label: '香气' },
  { key: 'flavor', label: '风味' },
  { key: 'aftertaste', label: '余韵' },
  { key: 'acidity', label: '酸质' },
  { key: 'body', label: '触感' },
  { key: 'balance', label: '平衡度' },
]

const PARAM_FIELDS: { key: string; label: string; placeholder: string }[] = [
  { key: 'device', label: '滤杯', placeholder: '例如 V60' },
  { key: 'grinder', label: '磨豆机', placeholder: '例如 ZP6S' },
  { key: 'grind_setting', label: '研磨刻度', placeholder: '例如 4.5-5.5 圈' },
  { key: 'dose_g', label: '豆量 (g)', placeholder: '15' },
  { key: 'water_ml', label: '水量 (ml)', placeholder: '225' },
  { key: 'water_temp_c', label: '水温 (°C)', placeholder: '92' },
  { key: 'ratio', label: '粉水比', placeholder: '1:15' },
  { key: 'time', label: '时间', placeholder: '2:30 或 150（秒）' },
]

interface ComponentDraft {
  origin_name: string
  coffee_source_name: string
  process_name: string
  varietalsText: string
  altitude_text: string
  share_text: string
  notes: string
}

interface EditState {
  fields: Record<string, string>
  varietalsText: string
  flavorNotesText: string
  axes: FlavorAxis[]
  rating: BrewEvaluation | null
  privateNotes: string
  publicComment: string
  params: Record<string, string>
  components: ComponentDraft[]
}

function componentToDraft(component: BeanComponent): ComponentDraft {
  return {
    origin_name: component.origin_name ?? '',
    coffee_source_name: component.coffee_source_name ?? '',
    process_name: component.process_name ?? '',
    varietalsText: (component.varietal_names ?? []).join('，'),
    altitude_text: component.altitude_text ?? '',
    share_text: component.share_text ?? '',
    notes: component.notes ?? '',
  }
}

function draftToComponent(component: ComponentDraft): BeanComponent {
  return {
    origin_name: optionalText(component.origin_name),
    coffee_source_name: optionalText(component.coffee_source_name),
    process_name: optionalText(component.process_name),
    varietal_names: splitList(component.varietalsText),
    altitude_text: optionalText(component.altitude_text),
    share_text: optionalText(component.share_text),
    notes: optionalText(component.notes),
  }
}

function beanToEdit(bean: Bean): EditState {
  const p = bean.recommended_params
  return {
    fields: Object.fromEntries(FIELD_DEFS.map(({ draftKey, beanKey }) => [
      draftKey, String((bean[beanKey] as string | null | undefined) ?? ''),
    ])),
    varietalsText: bean.varietal.join('，'),
    flavorNotesText: bean.flavor.notes.join('，'),
    axes: (bean.flavor.axes ?? []).map(a => ({ label: a.label, value: a.value ?? null })),
    rating: bean.rating ?? null,
    privateNotes: bean.private_notes ?? '',
    publicComment: bean.public_comment ?? '',
    components: (bean.bean_components ?? []).map(componentToDraft),
    params: {
      device: p?.device ?? '',
      grinder: p?.grinder ?? '',
      grind_setting: p?.grind_setting ?? '',
      dose_g: p?.dose_g != null ? String(p.dose_g) : '',
      water_ml: p?.water_ml != null ? String(p.water_ml) : '',
      water_temp_c: p?.water_temp_c != null ? String(p.water_temp_c) : '',
      ratio: p?.ratio ?? '',
      time: formatBrewSeconds(p?.brew_time_seconds) ?? '',
    },
  }
}

function optionalText(text: string): string | null {
  const trimmed = text.trim()
  return trimmed ? trimmed : null
}

function setRatingScore(rating: BrewEvaluation | null, key: keyof BrewEvaluation, score: number | null): BrewEvaluation | null {
  const next: BrewEvaluation = { ...(rating ?? {}) }
  const current = next[key] as BrewEvaluationItem | undefined
  if (score == null) {
    if (current?.description) next[key] = { description: current.description }
    else delete next[key]
  } else {
    next[key] = { ...(current ?? {}), score }
  }
  return Object.keys(next).length > 0 ? next : null
}

function parseTimeText(text: string): number | undefined {
  const t = text.trim()
  if (!t) return undefined
  const m = t.match(/^(\d+)[:：](\d{1,2})$/)
  if (m) return Number(m[1]) * 60 + Number(m[2])
  const n = Number(t)
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : undefined
}

function splitList(text: string): string[] {
  return text.split(/[，,]/).map(s => s.trim()).filter(Boolean)
}

function hasText(value?: string | null): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function hasFlavor(bean: Bean): boolean {
  return (bean.flavor.notes?.length ?? 0) > 0 || (bean.flavor.axes?.length ?? 0) > 0
}

function Dots({ value, max = 5, onSelect }: { value?: number | null; max?: number; onSelect?: (v: number | null) => void }) {
  const safeMax = Math.max(1, Math.round(max))
  const safeValue = Math.max(0, Math.min(safeMax, Math.round(value ?? 0)))
  return (
    <div className="flex gap-1">
      {Array.from({ length: safeMax }, (_, index) => (
        <span
          key={index}
          onClick={onSelect ? () => onSelect(index + 1 === safeValue ? null : index + 1) : undefined}
          className={`w-2.5 h-2.5 rounded-full border transition-colors ${
            index < safeValue ? 'bg-dc-accent border-dc-accent' : 'border-dc-border'
          } ${onSelect ? 'cursor-pointer hover:border-dc-accent' : ''}`}
        />
      ))}
    </div>
  )
}

function FieldView({ label, value }: { label: string; value?: string | null }) {
  if (!hasText(value)) return null
  return (
    <div>
      <div className="text-xs text-dc-text-3 mb-0.5">{label}</div>
      <div className="text-sm font-medium text-dc-text-1">{value}</div>
    </div>
  )
}

function FieldInput({ label, value, onChange, required, placeholder }: {
  label: string
  value: string
  onChange: (v: string) => void
  required?: boolean
  placeholder?: string
}) {
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">
        {label}{required && <span className="text-dc-red"> *</span>}
      </span>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder ?? '未填写'}
        className="dc-input text-sm py-1.5"
      />
    </label>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="dc-card p-5">
      <h2 className="section-title mb-4">{title}</h2>
      {children}
    </div>
  )
}

export default function BeanDetailPage() {
  const params = useParams()
  const id = typeof params.id === 'string' ? params.id : Array.isArray(params.id) ? params.id[0] : ''
  const [bean, setBean] = useState<Bean | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState<EditState | null>(null)
  const initialEditRef = useRef<string>('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getBean(id, getToken())
      .then((item) => { if (!cancelled) setBean(item) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : '豆卡加载失败，请稍后重试。') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [id])

  function enterEdit() {
    if (!bean) return
    const next = beanToEdit(bean)
    initialEditRef.current = JSON.stringify(next)
    setEdit(next)
    setSaveError('')
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
    setEdit(null)
    setSaveError('')
  }

  function setField(key: string, value: string) {
    if (!edit) return
    setEdit({ ...edit, fields: { ...edit.fields, [key]: value } })
  }

  function setComponent(index: number, patch: Partial<ComponentDraft>) {
    if (!edit) return
    setEdit({
      ...edit,
      components: edit.components.map((component, i) => i === index ? { ...component, ...patch } : component),
    })
  }

  async function save() {
    if (!bean || !edit) return
    const requiredMissing = FIELD_DEFS
      .filter(field => field.required && !edit.fields[field.draftKey]?.trim())
      .map(field => field.label)
    if (requiredMissing.length > 0) {
      setSaveError(`请填写：${requiredMissing.join('、')}`)
      return
    }

    setSaving(true)
    setSaveError('')
    try {
      const token = getToken()
      const initial = JSON.parse(initialEditRef.current) as EditState
      const patch: Record<string, unknown> = {}

      for (const { draftKey } of FIELD_DEFS) {
        if (edit.fields[draftKey] !== initial.fields[draftKey]) {
          patch[draftKey] = edit.fields[draftKey].trim() || null
        }
      }
      if (edit.varietalsText !== initial.varietalsText) patch.varietal_names = splitList(edit.varietalsText)
      if (edit.privateNotes !== initial.privateNotes) patch.private_notes = edit.privateNotes.trim() || null
      if (edit.publicComment !== initial.publicComment) patch.public_comment = edit.publicComment.trim() || null
      if (JSON.stringify(edit.components) !== JSON.stringify(initial.components)) {
        patch.bean_components = edit.components.map(draftToComponent)
      }
      const flavorDirty = edit.flavorNotesText !== initial.flavorNotesText
        || JSON.stringify(edit.axes) !== JSON.stringify(initial.axes)
      if (flavorDirty) {
        patch.flavor = {
          notes: splitList(edit.flavorNotesText),
          source: 'roaster',
          scale_max: 5,
          axes: edit.axes.filter(axis => axis.label.trim()).map(axis => ({
            label: axis.label.trim(),
            value: axis.value ?? null,
          })),
        }
      }
      if (JSON.stringify(edit.rating) !== JSON.stringify(initial.rating)) patch.rating = edit.rating

      const paramsDirty = JSON.stringify(edit.params) !== JSON.stringify(initial.params)
      const paramValues: ManualRecommendParams = {
        device: edit.params.device.trim() || undefined,
        grinder: edit.params.grinder.trim() || undefined,
        grind_setting: edit.params.grind_setting.trim() || undefined,
        dose_g: edit.params.dose_g.trim() ? Number(edit.params.dose_g) : undefined,
        water_ml: edit.params.water_ml.trim() ? Number(edit.params.water_ml) : undefined,
        water_temp_c: edit.params.water_temp_c.trim() ? Number(edit.params.water_temp_c) : undefined,
        ratio: edit.params.ratio.trim() || undefined,
        brew_time_seconds: parseTimeText(edit.params.time),
      }
      const hasParamValue = Object.values(paramValues).some(v => v !== undefined)

      if (Object.keys(patch).length > 0) await updateBean(bean.bean_id, patch as BeanUpdateInput, token)
      if (paramsDirty && hasParamValue) await setManualRecommendParams(bean.bean_id, paramValues, token)

      const fresh = await getBean(bean.bean_id, token)
      if (fresh) setBean(fresh)
      setEditing(false)
      setEdit(null)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <BackLink />
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆卡…</div>
      </div>
    )
  }

  if (error && !bean) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <BackLink />
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">豆卡暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      </div>
    )
  }

  if (!bean) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <BackLink />
        <div className="dc-card p-8 text-center">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有找到这张豆卡</div>
          <p className="text-sm text-dc-text-3">它可能已被删除，或当前账户没有权限查看。</p>
        </div>
      </div>
    )
  }

  const paramRows = recommendedParamRows(bean.recommended_params)
  const beanScore = bean.rating?.overall?.score ?? bean.avg_score
  const summaryOrigin = (bean.bean_components?.length ?? 0) > 1 ? '多产地 / 拼配' : bean.origin
  const summaryProcess = (bean.bean_components?.length ?? 0) > 1 ? '多处理法' : bean.process

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <BackLink />

      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-dc-text-1 mb-2">{bean.name}</h1>
          {!editing && (
            <div className="flex flex-wrap gap-2">
              {bean.roaster && <span className="dc-tag">{bean.roaster}</span>}
              {summaryOrigin && <span className="dc-tag">{summaryOrigin}</span>}
              {summaryProcess && <span className="dc-tag">{summaryProcess}</span>}
            </div>
          )}
          {editing && <p className="text-xs text-dc-text-3">豆卡名称创建后固定；如果是另一支豆，请新建豆卡。</p>}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {editing ? (
            <>
              <button onClick={cancelEdit} disabled={saving} className="btn-secondary text-sm px-4 py-2">取消</button>
              <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin inline" /> : '保存'}
              </button>
            </>
          ) : (
            <>
              <button onClick={enterEdit} className="btn-secondary text-sm px-3.5 py-2 flex items-center gap-1.5">
                <Pencil size={13} />
                编辑
              </button>
              {beanScore !== null && beanScore !== undefined && (
                <div className="w-14 h-14 rounded-full bg-dc-accent-light flex items-center justify-center flex-shrink-0">
                  <div className="text-center">
                    <span className="text-xl font-extrabold text-dc-accent">{beanScore}</span>
                    <span className="text-xs text-dc-text-3 block leading-none">/5</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {saveError && <div className="mb-4 text-sm text-dc-red">{saveError}</div>}

      {editing && edit ? (
        <div className="max-w-3xl space-y-5">
          <Section title="豆卡信息">
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
              {FIELD_DEFS.map(({ draftKey, label, required }) => (
                <FieldInput
                  key={draftKey}
                  label={label}
                  required={required}
                  value={edit.fields[draftKey]}
                  onChange={value => setField(draftKey, value)}
                />
              ))}
              <FieldInput
                label="品种"
                value={edit.varietalsText}
                onChange={value => setEdit({ ...edit, varietalsText: value })}
                placeholder="例如：瑰夏，SL9"
              />
            </div>
          </Section>

          <Section title="豆源组成">
            {edit.components.length === 0 ? (
              <p className="text-sm text-dc-text-3 mb-3">单一豆源可以不填；拼配或多产地产品建议逐条记录。</p>
            ) : (
              <div className="space-y-4 mb-4">
                {edit.components.map((component, index) => (
                  <div key={index} className="border border-dc-border rounded-lg p-3">
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-sm font-medium text-dc-text-1">豆源 {index + 1}</div>
                      <button
                        type="button"
                        onClick={() => setEdit({ ...edit, components: edit.components.filter((_, i) => i !== index) })}
                        className="text-dc-red hover:bg-dc-red/5 rounded-md p-1"
                        aria-label="删除豆源"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3">
                      <FieldInput label="产地" value={component.origin_name} onChange={value => setComponent(index, { origin_name: value })} />
                      <FieldInput label="生产者 / 庄园 / 处理站" value={component.coffee_source_name} onChange={value => setComponent(index, { coffee_source_name: value })} />
                      <FieldInput label="处理法" value={component.process_name} onChange={value => setComponent(index, { process_name: value })} />
                      <FieldInput label="品种" value={component.varietalsText} onChange={value => setComponent(index, { varietalsText: value })} />
                      <FieldInput label="海拔" value={component.altitude_text} onChange={value => setComponent(index, { altitude_text: value })} />
                      <FieldInput label="占比 / 说明" value={component.share_text} onChange={value => setComponent(index, { share_text: value })} />
                    </div>
                    <label className="block mt-3">
                      <span className="text-xs text-dc-text-3 mb-1 block">备注</span>
                      <textarea
                        value={component.notes}
                        onChange={event => setComponent(index, { notes: event.target.value })}
                        className="dc-input text-sm min-h-[64px] resize-none leading-relaxed"
                      />
                    </label>
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={() => setEdit({
                ...edit,
                components: [...edit.components, {
                  origin_name: '',
                  coffee_source_name: '',
                  process_name: '',
                  varietalsText: '',
                  altitude_text: '',
                  share_text: '',
                  notes: '',
                }],
              })}
              className="btn-secondary text-sm px-3 py-2 inline-flex items-center gap-1.5"
            >
              <Plus size={14} />
              添加豆源
            </button>
          </Section>

          <Section title="风味信息">
            <div className="mb-4">
              <FieldInput
                label="风味标签"
                value={edit.flavorNotesText}
                onChange={value => setEdit({ ...edit, flavorNotesText: value })}
                placeholder="例如：花香，荔枝，红酒"
              />
            </div>
            <div className="space-y-3">
              {edit.axes.map((axis, index) => (
                <div key={index} className="grid sm:grid-cols-[1fr_auto_auto] gap-3 items-center">
                  <input
                    value={axis.label}
                    onChange={event => setEdit({ ...edit, axes: edit.axes.map((item, i) => i === index ? { ...item, label: event.target.value } : item) })}
                    placeholder="维度名称，例如 酸"
                    className="dc-input text-sm py-1.5"
                  />
                  <Dots
                    value={axis.value}
                    onSelect={value => setEdit({ ...edit, axes: edit.axes.map((item, i) => i === index ? { ...item, value } : item) })}
                  />
                  <button
                    type="button"
                    onClick={() => setEdit({ ...edit, axes: edit.axes.filter((_, i) => i !== index) })}
                    className="text-dc-red hover:bg-dc-red/5 rounded-md p-1 justify-self-start sm:justify-self-auto"
                    aria-label="删除风味维度"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setEdit({ ...edit, axes: [...edit.axes, { label: '', value: null }] })}
              className="btn-secondary text-sm px-3 py-2 inline-flex items-center gap-1.5 mt-4"
            >
              <Plus size={14} />
              添加维度
            </button>
          </Section>

          <Section title="评分">
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
              {RATING_FIELDS.map(({ key, label }) => {
                const item = edit.rating?.[key]
                return (
                  <div key={key} className="flex items-center justify-between gap-3">
                    <span className="text-sm text-dc-text-2">{label}</span>
                    <div className="flex items-center gap-2">
                      <Dots value={item?.score} onSelect={value => setEdit({ ...edit, rating: setRatingScore(edit.rating, key, value) })} />
                      {item?.score !== undefined && <span className="text-xs font-semibold text-dc-accent w-7 text-right">{item.score}/5</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>

          <Section title="建议冲煮参数">
            <div className="space-y-2.5">
              {PARAM_FIELDS.map(({ key, label, placeholder }) => (
                <div key={key} className="flex items-center justify-between gap-3">
                  <span className="text-xs text-dc-text-3 flex-shrink-0 w-20">{label}</span>
                  <input
                    value={edit.params[key]}
                    onChange={event => setEdit({ ...edit, params: { ...edit.params, [key]: event.target.value } })}
                    placeholder={placeholder}
                    className="dc-input text-sm py-1.5 text-right flex-1 min-w-0"
                  />
                </div>
              ))}
            </div>
          </Section>

          <Section title="备注">
            <p className="text-xs text-dc-text-3 mb-2">仅本人可见。</p>
            <textarea
              value={edit.privateNotes}
              onChange={event => setEdit({ ...edit, privateNotes: event.target.value })}
              placeholder="采收期、购买渠道、豆袋长文、个人备注…"
              className="dc-input text-sm min-h-[120px] resize-none leading-relaxed"
            />
          </Section>

          <Section title="评论">
            <p className="text-xs text-dc-text-3 mb-2">评论会被公开，其他用户看到该豆卡时，会看到您的匿名评论。</p>
            <textarea
              value={edit.publicComment}
              onChange={event => setEdit({ ...edit, publicComment: event.target.value })}
              placeholder="写下这支豆子的公开评价、购买印象或冲煮感受…"
              className="dc-input text-sm min-h-[100px] resize-none leading-relaxed"
            />
          </Section>
        </div>
      ) : (
        <div className="grid md:grid-cols-[1fr_300px] gap-6 items-start">
          <div className="space-y-5">
            <Section title="豆卡信息">
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
                {FIELD_DEFS.map(({ draftKey, beanKey, label }) => (
                  <FieldView key={draftKey} label={label} value={bean[beanKey] as string | null | undefined} />
                ))}
                <FieldView label="品种" value={bean.varietal.join(' / ')} />
              </div>
            </Section>

            {(bean.bean_components?.length ?? 0) > 0 && (
              <Section title="豆源组成">
                <div className="space-y-3">
                  {bean.bean_components.map((component, index) => {
                    const details = [
                      component.origin_name,
                      component.coffee_source_name,
                      component.process_name,
                      component.varietal_names?.join(' / '),
                      component.altitude_text,
                      component.share_text,
                    ].filter(Boolean).join(' · ')
                    return (
                      <div key={index} className="border border-dc-border rounded-lg p-3">
                        <div className="text-sm font-medium text-dc-text-1 mb-1">豆源 {index + 1}</div>
                        {details && <div className="text-sm text-dc-text-2 leading-relaxed">{details}</div>}
                        {component.notes && <div className="text-sm text-dc-text-3 leading-relaxed mt-1">{component.notes}</div>}
                      </div>
                    )
                  })}
                </div>
              </Section>
            )}

            {hasFlavor(bean) && (
              <Section title="风味信息">
                {bean.flavor.notes.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-4">
                    {bean.flavor.notes.map((note) => <span key={note} className="dc-tag">{note}</span>)}
                  </div>
                )}
                {bean.flavor.axes.length > 0 && (
                  <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3 pt-3 border-t border-dc-border">
                    {bean.flavor.axes.map((axis) => (
                      <div key={axis.label} className="flex items-center justify-between gap-3">
                        <span className="text-sm text-dc-text-2">{axis.label}</span>
                        <Dots value={axis.value} max={bean.flavor.scale_max} />
                      </div>
                    ))}
                  </div>
                )}
              </Section>
            )}

            <Section title="评分">
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
                {RATING_FIELDS.map(({ key, label }) => {
                  const item = bean.rating?.[key]
                  return (
                    <div key={key} className="flex items-center justify-between gap-3">
                      <span className="text-sm text-dc-text-2">{label}</span>
                      <div className="flex items-center gap-2">
                        <Dots value={item?.score} />
                        {item?.score !== undefined && <span className="text-xs font-semibold text-dc-accent w-7 text-right">{item.score}/5</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </Section>

            {bean.private_notes && (
              <Section title="备注">
                <p className="text-xs text-dc-text-3 mb-2">仅本人可见。</p>
                <p className="text-sm text-dc-text-2 leading-relaxed whitespace-pre-line">{bean.private_notes}</p>
              </Section>
            )}

            {bean.public_comment && (
              <Section title="评论">
                <p className="text-xs text-dc-text-3 mb-2">会以匿名评论展示在豆仓广场。</p>
                <p className="text-sm text-dc-text-2 leading-relaxed whitespace-pre-line">{bean.public_comment}</p>
              </Section>
            )}
          </div>

          <div className="space-y-5">
            <Section title="建议冲煮参数">
              {paramRows.length > 0 ? (
                <div className="space-y-3">
                  {paramRows.map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-3 text-sm">
                      <span className="text-dc-text-3 flex-shrink-0">{label}</span>
                      <span className="font-medium text-dc-text-1 text-right">{value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-dc-text-3 leading-relaxed">暂无建议参数，可以由 Coffea 生成、手动编辑填写，或从一条冲煮记录设为建议值。</p>
              )}
              <div className="mt-4">
                <RecommendParamsChat
                  beanId={bean.bean_id}
                  hasParams={paramRows.length > 0}
                  onCompleted={(params, recordId) =>
                    setBean((b) => b ? { ...b, recommended_params: params, recommended_record_id: recordId, updated_at: new Date().toISOString() } : b)
                  }
                />
              </div>
            </Section>

            <Link href={`/app/records?bean=${encodeURIComponent(bean.name)}&bean_id=${encodeURIComponent(bean.bean_id)}`} className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block">
              <div className="w-9 h-9 rounded-full bg-dc-accent-light flex-shrink-0 flex items-center justify-center">
                <ClipboardList size={16} className="text-dc-accent" strokeWidth={1.8} />
              </div>
              <div>
                <div className="text-sm font-medium text-dc-text-1">查看冲煮记录</div>
                <div className="text-xs text-dc-text-3">共 {bean.record_count} 条</div>
              </div>
            </Link>

            <Link href={`/app/chat?new=1&bean_id=${encodeURIComponent(bean.bean_id)}`} className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block">
              <div className="w-9 h-9 rounded-full bg-dc-accent flex-shrink-0 flex items-center justify-center">
                <MessageSquare size={16} className="text-white" strokeWidth={1.8} />
              </div>
              <div>
                <div className="text-sm font-medium text-dc-text-1">记录一次冲煮</div>
                <div className="text-xs text-dc-text-3">自动关联到这张豆卡</div>
              </div>
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

function BackLink() {
  return (
    <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
      <ArrowLeft size={15} />
      返回豆仓
    </Link>
  )
}
