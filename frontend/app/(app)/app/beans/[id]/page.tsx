'use client'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import { ArrowLeft, ClipboardList, Loader2, MessageSquare, Pencil } from 'lucide-react'
import { getBean, updateBean, setManualRecommendParams, type ManualRecommendParams } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { formatBrewSeconds, recommendedParamRows } from '@/lib/beans'
import { RecommendParamsChat } from '@/components/RecommendParamsChat'
import type { Bean, BeanDraft, FlavorAxis } from '@/types'

// 默认五维风味模板（与后端 default_flavor 一致），axes 为空时用作展示占位与编辑底板
const DEFAULT_AXES = ['酸质', '甜感', '醇厚', '余韵', '发酵感']

const FIELD_DEFS: { draftKey: keyof BeanDraft & string; beanKey: keyof Bean & string; label: string }[] = [
  { draftKey: 'roaster_name', beanKey: 'roaster', label: '烘焙商' },
  { draftKey: 'roaster_product_name', beanKey: 'roaster_product', label: '烘焙商产品' },
  { draftKey: 'coffee_source_name', beanKey: 'coffee_source', label: '生产者/庄园/处理站' },
  { draftKey: 'green_bean_merchant_name', beanKey: 'green_bean_merchant', label: '生豆商/进口商' },
  { draftKey: 'green_bean_product_name', beanKey: 'green_bean_product', label: '生豆商产品' },
  { draftKey: 'origin_name', beanKey: 'origin', label: '产地' },
  { draftKey: 'process_name', beanKey: 'process', label: '处理法' },
]

interface EditState {
  name: string
  fields: Record<string, string>   // draftKey -> 文本
  varietalsText: string
  flavorNotesText: string
  axes: FlavorAxis[]
  scaleMax: number
  privateNotes: string
  params: Record<string, string>   // device/grinder/grind_setting/dose_g/water_ml/water_temp_c/ratio/time
}

function beanToEdit(bean: Bean): EditState {
  const axes = bean.flavor.axes.length > 0
    ? bean.flavor.axes.map(a => ({ label: a.label, value: a.value ?? null }))
    : DEFAULT_AXES.map(label => ({ label, value: null }))
  const p = bean.recommended_params
  return {
    name: bean.name,
    fields: Object.fromEntries(FIELD_DEFS.map(({ draftKey, beanKey }) => [
      draftKey, String((bean[beanKey] as string | null | undefined) ?? ''),
    ])),
    varietalsText: bean.varietal.join('，'),
    flavorNotesText: bean.flavor.notes.join('，'),
    axes,
    scaleMax: bean.flavor.scale_max || 5,
    privateNotes: bean.private_notes ?? '',
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

// 时间输入：支持 "2:30" 或纯秒 "150"
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

// 查看态字段：常驻占位，未填显示「—」
function FieldView({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-xs text-dc-text-3 mb-0.5">{label}</div>
      {value ? (
        <div className="text-sm font-medium text-dc-text-1">{value}</div>
      ) : (
        <div className="text-sm text-dc-text-3">—</div>
      )}
    </div>
  )
}

function FieldInput({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div>
      <div className="text-xs text-dc-text-3 mb-0.5">{label}</div>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder ?? '未填写'}
        className="dc-input text-sm py-1.5"
      />
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
      .then((item) => {
        if (!cancelled) setBean(item)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '豆卡加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
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

  async function save() {
    if (!bean || !edit) return
    if (!edit.name.trim()) {
      setSaveError('豆名不能为空')
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      const token = getToken()
      const initial = JSON.parse(initialEditRef.current) as EditState

      // 豆卡字段 + 品种 + 风味 + 备注 → PATCH（只在有变化时发对应键；空串显式发 null 以清空）
      const patch: Record<string, unknown> = {}
      if (edit.name.trim() !== initial.name) patch.name = edit.name.trim()
      for (const { draftKey } of FIELD_DEFS) {
        if (edit.fields[draftKey] !== initial.fields[draftKey]) {
          patch[draftKey] = edit.fields[draftKey].trim() || null
        }
      }
      if (edit.varietalsText !== initial.varietalsText) patch.varietal_names = splitList(edit.varietalsText)
      if (edit.privateNotes !== initial.privateNotes) patch.private_notes = edit.privateNotes.trim() || null
      const flavorDirty = edit.flavorNotesText !== initial.flavorNotesText
        || JSON.stringify(edit.axes) !== JSON.stringify(initial.axes)
      if (flavorDirty) {
        patch.flavor = {
          notes: splitList(edit.flavorNotesText),
          source: 'user',
          scale_max: edit.scaleMax,
          axes: edit.axes,
        }
      }

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

      if (Object.keys(patch).length > 0) {
        await updateBean(bean.bean_id, patch as Partial<BeanDraft>, token)
      }
      if (paramsDirty && hasParamValue) {
        await setManualRecommendParams(bean.bean_id, paramValues, token)
      }
      // 以服务端为准刷新整卡
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
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆卡…</div>
      </div>
    )
  }

  if (error && !bean) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
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
        <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回豆仓
        </Link>
        <div className="dc-card p-8 text-center">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有找到这张豆卡</div>
          <p className="text-sm text-dc-text-3">它可能已被删除，或当前账户没有权限查看。</p>
        </div>
      </div>
    )
  }

  const paramRows = recommendedParamRows(bean.recommended_params)
  const viewAxes: FlavorAxis[] = bean.flavor.axes.length > 0
    ? bean.flavor.axes
    : DEFAULT_AXES.map(label => ({ label, value: null }))

  const PARAM_FIELDS: { key: string; label: string; placeholder: string }[] = [
    { key: 'device', label: '滤杯', placeholder: '例如 V60' },
    { key: 'grinder', label: '磨豆机', placeholder: '例如 ZP6S' },
    { key: 'grind_setting', label: '研磨刻度', placeholder: '例如 4.5–5.5 圈' },
    { key: 'dose_g', label: '豆量 (g)', placeholder: '15' },
    { key: 'water_ml', label: '水量 (ml)', placeholder: '225' },
    { key: 'water_temp_c', label: '水温 (°C)', placeholder: '92' },
    { key: 'ratio', label: '粉水比', placeholder: '1:15' },
    { key: 'time', label: '时间', placeholder: '2:30 或 150（秒）' },
  ]

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
        <ArrowLeft size={15} />
        返回豆仓
      </Link>

      {/* Header：标题 + 标签 + 编辑/保存操作 */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex-1 min-w-0">
          {editing && edit ? (
            <input
              value={edit.name}
              onChange={e => setEdit({ ...edit, name: e.target.value })}
              className="dc-input text-lg font-bold mb-2 max-w-md"
              placeholder="豆卡名称"
            />
          ) : (
            <h1 className="text-xl font-bold text-dc-text-1 mb-2">{bean.name}</h1>
          )}
          {!editing && (
            <div className="flex flex-wrap gap-2">
              {bean.roaster && <span className="dc-tag">{bean.roaster}</span>}
              {bean.origin && <span className="dc-tag">{bean.origin}</span>}
              {bean.process && <span className="dc-tag">{bean.process}</span>}
            </div>
          )}
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
              {bean.avg_score !== null && bean.avg_score !== undefined && (
                <div className="w-14 h-14 rounded-full bg-dc-accent-light flex items-center justify-center flex-shrink-0">
                  <div className="text-center">
                    <span className="text-xl font-extrabold text-dc-accent">{bean.avg_score}</span>
                    <span className="text-xs text-dc-text-3 block leading-none">/5</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {saveError && <div className="mb-4 text-sm text-dc-red">{saveError}</div>}

      <div className="grid md:grid-cols-[1fr_300px] gap-6 items-start">
        <div className="space-y-5">
          {/* 豆卡信息：全部字段常驻（含未填占位） */}
          <div className="dc-card p-5">
            <h2 className="section-title mb-4">豆卡信息</h2>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
              {FIELD_DEFS.map(({ draftKey, beanKey, label }) => (
                editing && edit ? (
                  <FieldInput
                    key={draftKey}
                    label={label}
                    value={edit.fields[draftKey]}
                    onChange={v => setEdit({ ...edit, fields: { ...edit.fields, [draftKey]: v } })}
                  />
                ) : (
                  <FieldView key={draftKey} label={label} value={bean[beanKey] as string | null | undefined} />
                )
              ))}
              {editing && edit ? (
                <FieldInput
                  label="品种（逗号分隔）"
                  value={edit.varietalsText}
                  onChange={v => setEdit({ ...edit, varietalsText: v })}
                  placeholder="例如：瑰夏，帕卡马拉"
                />
              ) : (
                <FieldView label="品种" value={bean.varietal.join(' / ')} />
              )}
            </div>
          </div>

          {/* 风味信息：标签 + 维度均常驻 */}
          <div className="dc-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="section-title">风味信息</h2>
              <span className="text-xs text-dc-text-3">
                {bean.flavor.source === 'roaster' ? '烘焙商维度' : bean.flavor.source === 'user' ? '用户维度' : '默认维度'}
              </span>
            </div>

            {editing && edit ? (
              <div className="mb-4">
                <div className="text-xs text-dc-text-3 mb-0.5">风味标签（逗号分隔）</div>
                <input
                  value={edit.flavorNotesText}
                  onChange={e => setEdit({ ...edit, flavorNotesText: e.target.value })}
                  placeholder="例如：草莓，奶油，红酒"
                  className="dc-input text-sm py-1.5"
                />
              </div>
            ) : bean.flavor.notes.length > 0 ? (
              <div className="flex flex-wrap gap-2 mb-4">
                {bean.flavor.notes.map((note) => (
                  <span key={note} className="dc-tag">{note}</span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-dc-text-3 mb-4">未填写风味标签</p>
            )}

            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3 pt-3 border-t border-dc-border">
              {(editing && edit ? edit.axes : viewAxes).map((axis, i) => (
                <div key={axis.label} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-dc-text-2">{axis.label}</span>
                  <Dots
                    value={axis.value}
                    max={editing && edit ? edit.scaleMax : bean.flavor.scale_max}
                    onSelect={editing && edit
                      ? (v) => setEdit({ ...edit, axes: edit.axes.map((a, j) => j === i ? { ...a, value: v } : a) })
                      : undefined}
                  />
                </div>
              ))}
            </div>
            {editing && <p className="mt-2 text-[11px] text-dc-text-3">点击圆点打分，点当前分值可清除。</p>}
          </div>

          {/* 私有备注：常驻 */}
          <div className="dc-card p-5">
            <h2 className="section-title mb-3">私有备注</h2>
            {editing && edit ? (
              <textarea
                value={edit.privateNotes}
                onChange={e => setEdit({ ...edit, privateNotes: e.target.value })}
                placeholder="烘焙日期、海拔、购买渠道、个人印象…"
                className="dc-input text-sm min-h-[88px] resize-none leading-relaxed"
              />
            ) : bean.private_notes ? (
              <p className="text-sm text-dc-text-2 leading-relaxed whitespace-pre-line">{bean.private_notes}</p>
            ) : (
              <p className="text-sm text-dc-text-3">未填写</p>
            )}
          </div>
        </div>

        <div className="space-y-5">
          {/* 建议冲煮参数 */}
          <div className="dc-card p-5">
            <h2 className="section-title mb-4">建议冲煮参数</h2>
            {editing && edit ? (
              <div className="space-y-2.5">
                {PARAM_FIELDS.map(({ key, label, placeholder }) => (
                  <div key={key} className="flex items-center justify-between gap-3">
                    <span className="text-xs text-dc-text-3 flex-shrink-0 w-20">{label}</span>
                    <input
                      value={edit.params[key]}
                      onChange={e => setEdit({ ...edit, params: { ...edit.params, [key]: e.target.value } })}
                      placeholder={placeholder}
                      className="dc-input text-sm py-1.5 text-right flex-1 min-w-0"
                    />
                  </div>
                ))}
              </div>
            ) : paramRows.length > 0 ? (
              <div className="space-y-3">
                {paramRows.map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-3 text-sm">
                    <span className="text-dc-text-3 flex-shrink-0">{label}</span>
                    <span className="font-medium text-dc-text-1 text-right">{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-dc-text-3 leading-relaxed">
                暂无建议参数，可以由 Coffea 生成、手动编辑填写，或从一条冲煮记录设为建议值。
              </p>
            )}
            {!editing && (
              <div className="mt-4">
                <RecommendParamsChat
                  beanId={bean.bean_id}
                  hasParams={paramRows.length > 0}
                  onCompleted={(params, recordId) =>
                    setBean((b) =>
                      b
                        ? { ...b, recommended_params: params, recommended_record_id: recordId, updated_at: new Date().toISOString() }
                        : b,
                    )
                  }
                />
              </div>
            )}
          </div>

          <Link
            href={`/app/records?bean=${encodeURIComponent(bean.name)}`}
            className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block"
          >
            <div className="w-9 h-9 rounded-full bg-dc-accent-light flex-shrink-0 flex items-center justify-center">
              <ClipboardList size={16} className="text-dc-accent" strokeWidth={1.8} />
            </div>
            <div>
              <div className="text-sm font-medium text-dc-text-1">查看冲煮记录</div>
              <div className="text-xs text-dc-text-3">共 {bean.record_count} 条</div>
            </div>
          </Link>

          <Link
            href={`/app/chat?new=1&bean_id=${encodeURIComponent(bean.bean_id)}`}
            className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block"
          >
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
    </div>
  )
}
