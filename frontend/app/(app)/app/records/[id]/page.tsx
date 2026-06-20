'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, MessageSquare, Pencil, Trash2 } from 'lucide-react'
import { BrewRecordForm, type BrewRecordFormSubmit } from '@/components/BrewRecordForm'
import { getBeans } from '@/lib/api/beans'
import { createEquipment, listEquipment, type EquipmentProfile } from '@/lib/api/equipment'
import { deleteRecord, getComparisons, getRecord, updateRecord } from '@/lib/api/records'
import { getToken } from '@/lib/auth'
import type { Bean, BrewComparisonItem, BrewEvaluation, BrewRecord } from '@/types'
import SetRecommendedBtn from '@/components/SetRecommendedBtn'

function fmtTime(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function ScoreDots({ score }: { score?: number }) {
  if (score === undefined) return <span className="text-dc-text-3 text-xs">—</span>
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map(i => (
        <div
          key={i}
          className={`w-2 h-2 rounded-full border ${
            i <= score ? 'bg-dc-accent border-dc-accent' : 'border-dc-border bg-transparent'
          }`}
        />
      ))}
    </div>
  )
}

const EVAL_DIMENSIONS: { key: keyof BrewEvaluation; label: string }[] = [
  { key: 'overall',    label: '总评'  },
  { key: 'aroma',      label: '香气'  },
  { key: 'flavor',     label: '风味'  },
  { key: 'aftertaste', label: '余韵'  },
  { key: 'acidity',    label: '酸质'  },
  { key: 'body',       label: '触感'  },
  { key: 'balance',    label: '平衡度' },
]

type RecordEditForm = {
  bean_name: string
  brew_method: string
  device: string
  grinder: string
  grind_setting: string
  filter_media: string
  water: string
  dose_g: string
  water_ml: string
  water_temp_c: string
  ratio: string
  brew_time_seconds: string
  notes: string
}

function formFromRecord(record: BrewRecord): RecordEditForm {
  return {
    bean_name: record.bean_name ?? '',
    brew_method: record.brew_method ?? '',
    device: record.device ?? '',
    grinder: record.grinder ?? '',
    grind_setting: record.grind_setting ?? '',
    filter_media: record.filter_media ?? '',
    water: record.water ?? '',
    dose_g: record.dose_g != null ? String(record.dose_g) : '',
    water_ml: record.water_ml != null ? String(record.water_ml) : '',
    water_temp_c: record.water_temp_c != null ? String(record.water_temp_c) : '',
    ratio: record.ratio ?? '',
    brew_time_seconds: record.brew_time_seconds != null ? String(record.brew_time_seconds) : '',
    notes: record.notes ?? '',
  }
}

function optionalText(value: string): string | null {
  const text = value.trim()
  return text || null
}

function optionalNumber(value: string): number | null {
  const text = value.trim()
  if (!text) return null
  const n = Number(text)
  return Number.isFinite(n) && n > 0 ? n : null
}

export default function RecordDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = typeof params.id === 'string' ? params.id : Array.isArray(params.id) ? params.id[0] : ''
  const [record, setRecord] = useState<BrewRecord | null>(null)
  const [comparison, setComparison] = useState<BrewComparisonItem[]>([])
  const [beans, setBeans] = useState<Bean[]>([])
  const [equipment, setEquipment] = useState<EquipmentProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [actionError, setActionError] = useState('')

  useEffect(() => {
    const token = getToken()
    let cancelled = false
    setLoading(true)
    setError('')
    setRecord(null)
    setComparison([])

    Promise.all([getRecord(id, token), getBeans({}, token), listEquipment()])
      .then(async ([nextRecord, nextBeans, nextEquipment]) => {
        if (cancelled) return
        setRecord(nextRecord)
        setBeans(nextBeans)
        setEquipment(nextEquipment)
        if (nextRecord?.bean_name) {
          const nextComparison = await getComparisons(nextRecord.bean_name, token)
          if (!cancelled) {
            setComparison(nextComparison.map((item) => ({ ...item, active: item.id === nextRecord.id })))
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '冲煮记录加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [id])

  async function saveEdit(value: BrewRecordFormSubmit) {
    setSaving(true)
    setActionError('')
    try {
      const token = getToken()
      for (const item of value.equipmentToUpsert) {
        await createEquipment(item)
      }
      const updated = await updateRecord(id, value.payload as unknown as Record<string, unknown>, token)
      setRecord(updated)
      setEditing(false)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  async function removeRecord() {
    if (!record || !window.confirm(`删除「${record.bean_name ?? '这条冲煮记录'}」？`)) return
    setDeleting(true)
    setActionError('')
    try {
      await deleteRecord(record.id, getToken())
      router.push('/app/records')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '删除失败，请稍后重试。')
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/records" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回记录
        </Link>
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载冲煮记录…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/records" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回记录
        </Link>
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">记录暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      </div>
    )
  }

  if (!record) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/app/records" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回记录
        </Link>
        <div className="dc-card p-8 text-center">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有找到这条冲煮记录</div>
          <p className="text-sm text-dc-text-3">它可能已被删除，或当前账户没有权限查看。</p>
        </div>
      </div>
    )
  }

  const score = record.brew_score ?? undefined
  const date = record.created_at.slice(0, 10)
  const brewTime = record.brew_time ?? (record.brew_time_seconds ? fmtTime(record.brew_time_seconds) : undefined)
  const sensoryText = record.notes ?? record.evaluation?.overall?.description

  const brewParams: [string, string | undefined][] = [
    ['冲煮方式', record.brew_method ?? undefined],
    ['器具',     record.device],
    ['磨豆机',   record.grinder],
    ['过滤介质', record.filter_media ?? undefined],
    ['用水',     record.water ?? undefined],
    ['研磨刻度', record.grind_setting],
    ['豆重',     record.dose_g !== undefined ? `${record.dose_g} g` : undefined],
    ['水量',     record.water_ml !== undefined ? `${record.water_ml} ml` : undefined],
    ['粉水比',   record.ratio],
    ['水温',     record.water_temp_c !== undefined ? `${record.water_temp_c} °C` : undefined],
    ['冲煮时间', brewTime],
    ['烘焙商',   record.roaster],
  ]

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">

      {/* Back */}
      <Link href="/app/records" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
        <ArrowLeft size={15} />
        返回记录
      </Link>

      {/* Title row */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-dc-text-1 mb-1">{record.bean_name ?? '未命名记录'}</h1>
          <div className="flex gap-2 flex-wrap">
            {record.origin && <span className="dc-tag">{record.origin}</span>}
            {record.process && <span className="dc-tag">{record.process}</span>}
            {record.varietal && <span className="dc-tag">{record.varietal}</span>}
            <span className="text-xs text-dc-text-3">{date}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => { setEditing(true); setActionError('') }}
            className="btn-secondary text-sm flex items-center gap-1.5 py-2"
          >
            <Pencil size={14} /> 编辑
          </button>
          <button
            onClick={removeRecord}
            disabled={deleting}
            className="btn-secondary text-sm flex items-center gap-1.5 py-2 text-dc-red hover:text-dc-red disabled:opacity-50"
          >
            <Trash2 size={14} /> {deleting ? '删除中…' : '删除'}
          </button>
          {score !== undefined && (
            <div className="w-14 h-14 rounded-full bg-dc-accent-light flex items-center justify-center flex-shrink-0">
              <div className="text-center">
                <span className="text-xl font-extrabold text-dc-accent">{score}</span>
                <span className="text-xs text-dc-text-3 block leading-none">/5</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {actionError && (
        <div className="dc-card p-3 mb-5 text-sm text-dc-red bg-red-50 border-red-100">{actionError}</div>
      )}

      {editing ? (
        <div className="max-w-3xl">
          <BrewRecordForm
            mode="edit"
            record={record}
            beans={beans}
            equipment={equipment}
            saving={saving}
            onCancel={() => { setEditing(false); setActionError('') }}
            onSubmit={saveEdit}
          />
        </div>
      ) : (
        <div className="grid md:grid-cols-[1fr_300px] gap-6">
          {/* Left column */}
          <div className="space-y-5">

            {/* Brew params */}
            <div className="dc-card p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="section-title">冲煮参数</h2>
                <SetRecommendedBtn
                  beanCardId={record.bean_card_id}
                  recordId={record.id}
                />
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {brewParams.filter(([, v]) => v).map(([k, v]) => (
                  <div key={k}>
                    <div className="text-xs text-dc-text-3 mb-0.5">{k}</div>
                    <div className="text-sm font-medium text-dc-text-1">{v}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Notes */}
            {sensoryText && (
              <div className="dc-card p-5">
                <h2 className="section-title mb-3">感官记录</h2>
                <p className="text-sm text-dc-text-2 leading-relaxed">{sensoryText}</p>
              </div>
            )}

            {/* Brew steps */}
            <div className="dc-card p-5">
              <h2 className="section-title mb-4">冲煮阶段</h2>
              {record.brew_steps.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-dc-border text-xs text-dc-text-3">
                        <th className="text-left font-medium pb-2 w-8">段</th>
                        <th className="text-left font-medium pb-2 w-16">时间</th>
                        <th className="text-left font-medium pb-2 w-20">注水</th>
                        <th className="text-left font-medium pb-2">手法</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dc-border">
                      {record.brew_steps.map((step, i) => (
                        <tr key={i} className="text-dc-text-2">
                          <td className="py-2.5 text-dc-text-3 text-xs">{i + 1}</td>
                          <td className="py-2.5 font-mono text-xs">{fmtTime(step.time_seconds)}</td>
                          <td className="py-2.5 text-xs">
                            {step.water_ml !== undefined ? `${step.water_ml} ml` : <span className="text-dc-text-3">—</span>}
                          </td>
                          <td className="py-2.5 text-xs">{step.action}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-dc-text-3">暂无冲煮阶段数据</p>
              )}
            </div>

            {/* Detailed evaluation */}
            <div className="dc-card p-5">
              <h2 className="section-title mb-4">评分</h2>
              <div className="space-y-3">
                {EVAL_DIMENSIONS.map(({ key, label }) => {
                  const item = record.bean_rating?.[key]
                  return (
                    <div key={key} className="flex items-start gap-3">
                      <span className="text-xs text-dc-text-3 w-12 flex-shrink-0 pt-0.5">{label}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <ScoreDots score={item?.score} />
                          {item?.score !== undefined && (
                            <span className="text-xs font-semibold text-dc-accent">{item.score}/5</span>
                          )}
                        </div>
                        {item?.description && (
                          <p className="text-xs text-dc-text-3 leading-relaxed">{item.description}</p>
                        )}
                      </div>
                    </div>
                  )
                })}
                <div className="flex items-start gap-3 pt-3 border-t border-dc-border">
                  <span className="text-xs text-dc-text-3 w-20 flex-shrink-0 pt-0.5">本次冲煮</span>
                  <div className="flex items-center gap-2">
                    <ScoreDots score={record.brew_score ?? undefined} />
                    {record.brew_score !== undefined && record.brew_score !== null && (
                      <span className="text-xs font-semibold text-dc-accent">{record.brew_score}/5</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Raw input */}
            {record.raw_input?.trim() && (
              <div className="dc-card p-5">
                <h2 className="section-title mb-3">原始输入</h2>
                <blockquote className="border-l-2 border-dc-border pl-3 text-sm text-dc-text-3 italic leading-relaxed">
                  {record.raw_input}
                </blockquote>
              </div>
            )}

            {/* AI recap */}
            {record.recap && (
              <div className="bg-dc-accent-light border border-dc-accent/20 border-l-4 border-l-dc-accent rounded-xl p-5">
                <div className="text-xs font-bold text-dc-accent uppercase tracking-wide mb-2">AI 复盘</div>
                <p className="text-sm text-dc-text-1 leading-relaxed mb-3">{record.recap}</p>
                {record.suggestions.length > 0 && (
                  <div className="space-y-1.5">
                    {record.suggestions.map(s => (
                      <div key={s} className="flex gap-2 text-sm text-dc-text-2">
                        <span className="text-dc-accent flex-shrink-0">→</span>
                        {s}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right column */}
          <div className="space-y-5">
            {/* Same-bean comparison */}
            {comparison.length > 0 && (
              <div className="dc-card p-5">
                <h2 className="section-title mb-4">同豆对比</h2>
                <div className="space-y-2">
                  {comparison.map(c => (
                    <div
                      key={c.id}
                      className={`rounded-lg p-3 border text-xs ${
                        c.active
                          ? 'border-dc-accent bg-dc-accent-light'
                          : 'border-dc-border bg-dc-subtle'
                      }`}
                    >
                      <div className="flex justify-between items-center mb-2">
                        <span className={`font-medium ${c.active ? 'text-dc-accent' : 'text-dc-text-2'}`}>{c.date}</span>
                        {c.brew_score !== undefined && c.brew_score !== null && (
                          <span className={`font-bold ${c.active ? 'text-dc-accent' : 'text-dc-text-2'}`}>{c.brew_score}/5</span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-1 text-dc-text-3">
                        <span>{c.grinder} {c.grind_setting}</span>
                        {c.dose_g !== undefined && c.water_ml !== undefined && (
                          <span>{c.dose_g}g / {c.water_ml}ml</span>
                        )}
                        {c.water_temp_c !== undefined && <span>{c.water_temp_c}°C</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ask AI */}
            <Link
              href="/app/chat"
              className="dc-card p-5 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block"
            >
              <div className="w-9 h-9 rounded-full bg-dc-accent flex-shrink-0 flex items-center justify-center">
                <MessageSquare size={16} className="text-white" strokeWidth={1.8} />
              </div>
              <div>
                <div className="text-sm font-medium text-dc-text-1">问 AI</div>
                <div className="text-xs text-dc-text-3">关于这次冲煮继续追问</div>
              </div>
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
