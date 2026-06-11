'use client'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { ClipboardList, ExternalLink, Plus, Search, Settings2, X } from 'lucide-react'
import { getBeans } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { recommendedParamRows } from '@/lib/beans'
import { RecommendParamsChat } from '@/components/RecommendParamsChat'
import type { Bean } from '@/types'

interface CardTheme {
  frontBg: string
  backBg: string
  textMain: string
  textSub: string
  accent: string
  tagBg: string
}

function getTheme(process?: string | null): CardTheme {
  const p = process ?? ''
  if (p.includes('CM') || p.includes('厌氧')) {
    return {
      frontBg: 'linear-gradient(145deg, #EAF5EE 0%, #D6EDD9 100%)',
      backBg: 'linear-gradient(145deg, #D6EDD9 0%, #C4E2C8 100%)',
      textMain: '#1A3D28',
      textSub: '#4A7258',
      accent: '#2D6B42',
      tagBg: '#B8DEC0',
    }
  }
  if (p.includes('水洗')) {
    return {
      frontBg: 'linear-gradient(145deg, #EBF3FA 0%, #D5E8F5 100%)',
      backBg: 'linear-gradient(145deg, #D5E8F5 0%, #C0DAEA 100%)',
      textMain: '#12304A',
      textSub: '#3A6280',
      accent: '#2054A0',
      tagBg: '#B8D4EA',
    }
  }
  if (p.includes('日晒')) {
    return {
      frontBg: 'linear-gradient(145deg, #FEF4EC 0%, #FAE4CC 100%)',
      backBg: 'linear-gradient(145deg, #FAE4CC 0%, #F5D2B0 100%)',
      textMain: '#4A1A00',
      textSub: '#8A4820',
      accent: '#9B5E1A',
      tagBg: '#F2C89A',
    }
  }
  if (p.includes('蜜')) {
    return {
      frontBg: 'linear-gradient(145deg, #FFFAEC 0%, #FDF0C8 100%)',
      backBg: 'linear-gradient(145deg, #FDF0C8 0%, #FAE5A0 100%)',
      textMain: '#4A3000',
      textSub: '#8A6820',
      accent: '#8B6A14',
      tagBg: '#F5DA80',
    }
  }
  return {
    frontBg: 'linear-gradient(145deg, #FBF5EF 0%, #F2E6D8 100%)',
    backBg: 'linear-gradient(145deg, #F2E6D8 0%, #E8D4C0 100%)',
    textMain: '#3A1E0A',
    textSub: '#7A5038',
    accent: '#9B5E1A',
    tagBg: '#E5C8A8',
  }
}

function Dots({ value, max = 5, color }: { value?: number | null; max?: number; color: string }) {
  const safeMax = Math.max(1, Math.round(max))
  const safeValue = Math.max(0, Math.min(safeMax, Math.round(value ?? 0)))
  return (
    <div className="flex gap-1 items-center">
      {Array.from({ length: safeMax }, (_, i) => (
        <div
          key={i}
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: i < safeValue ? color : 'transparent',
            border: `1.5px solid ${color}`,
            opacity: i < safeValue ? 1 : 0.3,
          }}
        />
      ))}
    </div>
  )
}

function BrewRecordsBtn({ bean, textColor, bgColor }: { bean: Bean; textColor: string; bgColor: string }) {
  return (
    <Link
      href={`/app/records?bean=${encodeURIComponent(bean.name)}`}
      onClick={(event) => event.stopPropagation()}
      className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-opacity hover:opacity-70"
      style={{ background: bgColor, color: textColor }}
    >
      <ClipboardList size={11} />
      冲煮记录
    </Link>
  )
}

function ParamsBtn({
  bean,
  textColor,
  bgColor,
  onNoParams,
}: {
  bean: Bean
  textColor: string
  bgColor: string
  onNoParams: () => void
}) {
  const shared = {
    className: 'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-opacity hover:opacity-70',
    style: { background: bgColor, color: textColor } as CSSProperties,
  }

  const recordId = bean.recommended_params?.record_id ?? bean.recommended_record_id
  if (recordId) {
    return (
      <Link
        href={`/app/records/${recordId}`}
        onClick={(event) => event.stopPropagation()}
        {...shared}
      >
        <Settings2 size={11} />
        参数详情
      </Link>
    )
  }

  return (
    <button
      onClick={(event) => {
        event.stopPropagation()
        onNoParams()
      }}
      {...shared}
    >
      <Settings2 size={11} />
      生成参数
    </button>
  )
}

function BeanCard({ bean, onNoParams }: { bean: Bean; onNoParams: () => void }) {
  const [flipped, setFlipped] = useState(false)
  const theme = getTheme(bean.process)
  const flavor = bean.flavor
  const notes = flavor?.notes ?? []
  const axes = flavor?.axes ?? []
  const paramRows = recommendedParamRows(bean.recommended_params)
  const varietal = bean.varietal.length ? bean.varietal.join(' / ') : undefined

  return (
    <div
      className="relative w-full cursor-pointer select-none"
      style={{ perspective: '1400px', aspectRatio: '1/1' }}
      onClick={() => setFlipped((value) => !value)}
    >
      <div
        className="relative w-full h-full"
        style={{
          transformStyle: 'preserve-3d',
          transition: 'transform 0.48s cubic-bezier(0.4,0,0.2,1)',
          transform: flipped ? 'rotateY(180deg)' : 'rotateY(0)',
        }}
      >
        <div
          className="absolute inset-0 rounded-2xl overflow-hidden p-6 flex flex-col"
          style={{ backfaceVisibility: 'hidden', background: theme.frontBg }}
        >
          <div className="flex items-start justify-between mb-auto">
            <span className="text-xs font-medium" style={{ color: theme.textSub }}>
              {bean.roaster ?? '未填写烘焙商'}
            </span>
            <BrewRecordsBtn bean={bean} textColor={theme.textMain} bgColor={theme.tagBg} />
          </div>

          <div className="flex-1 flex items-center py-3">
            <h3 className="text-xl font-bold leading-snug line-clamp-3" style={{ color: theme.textMain }}>
              {bean.name}
            </h3>
          </div>

          {notes.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {notes.map((note) => (
                <span
                  key={note}
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: theme.tagBg, color: theme.textMain }}
                >
                  {note}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-end justify-between gap-3">
            <div className="flex flex-col gap-1.5 min-w-0">
              {bean.origin && (
                <span className="text-xs truncate" style={{ color: theme.textSub }}>{bean.origin}</span>
              )}
              {varietal && (
                <span className="text-xs truncate" style={{ color: theme.textSub }}>{varietal}</span>
              )}
              {bean.process && (
                <span
                  className="text-xs px-2 py-0.5 rounded-full font-medium w-fit"
                  style={{ background: theme.tagBg, color: theme.accent }}
                >
                  {bean.process}
                </span>
              )}
            </div>
            {bean.avg_score !== null && bean.avg_score !== undefined && (
              <div className="text-right flex-shrink-0">
                <div className="text-3xl font-black leading-none" style={{ color: theme.accent }}>
                  {bean.avg_score}
                </div>
                <div className="text-xs mt-0.5" style={{ color: theme.textSub }}>/5</div>
              </div>
            )}
          </div>
        </div>

        <div
          className="absolute inset-0 rounded-2xl overflow-hidden p-5 flex flex-col gap-3"
          style={{ backfaceVisibility: 'hidden', transform: 'rotateY(180deg)', background: theme.backBg }}
        >
          <div className="flex items-center justify-between flex-shrink-0 gap-2">
            <p className="text-xs font-semibold truncate flex-1" style={{ color: theme.textMain }}>
              {bean.name}
            </p>
            <ParamsBtn bean={bean} textColor={theme.textMain} bgColor={theme.tagBg} onNoParams={onNoParams} />
          </div>

          <div style={{ height: 1, background: theme.tagBg, flexShrink: 0 }} />

          <div className="flex-1 overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold" style={{ color: theme.accent }}>风味强度</p>
              <span className="text-[10px]" style={{ color: theme.textSub }}>
                {flavor?.source === 'roaster' ? '烘焙商维度' : '默认维度'}
              </span>
            </div>
            {axes.length > 0 ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {axes.map(({ label, value }) => (
                  <div key={label} className="flex items-center gap-2">
                    <span className="text-xs flex-shrink-0 truncate" style={{ color: theme.textSub, width: '3.5em' }}>
                      {label}
                    </span>
                    <Dots value={value} max={flavor?.scale_max} color={theme.accent} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs leading-relaxed" style={{ color: theme.textSub }}>暂未记录风味维度</p>
            )}
          </div>

          <div style={{ height: 1, background: theme.tagBg, flexShrink: 0 }} />

          <div className="flex-shrink-0">
            <p className="text-xs font-semibold mb-2" style={{ color: theme.accent }}>建议冲煮参数</p>
            {paramRows.length > 0 ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {paramRows.map(([key, value]) => (
                  <div key={key} className="flex gap-1.5 items-baseline">
                    <span className="text-xs flex-shrink-0" style={{ color: theme.textSub }}>{key}</span>
                    <span className="text-xs font-medium truncate" style={{ color: theme.textMain }}>{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs leading-relaxed" style={{ color: theme.textSub }}>
                暂无建议参数<br />可由 Coffea 生成或从冲煮记录设置
              </p>
            )}
          </div>

          <Link
            href={`/app/beans/${bean.bean_id}`}
            onClick={(event) => event.stopPropagation()}
            className="mt-auto flex items-center justify-center gap-1 text-xs font-medium py-1.5 rounded-full transition-opacity hover:opacity-70"
            style={{ background: theme.tagBg, color: theme.textMain }}
          >
            <ExternalLink size={11} />
            豆卡详情
          </Link>
        </div>
      </div>
    </div>
  )
}

const SCORE_FILTERS = [
  { label: '全部', min: 0 },
  { label: '≥ 4分', min: 4 },
  { label: '5分', min: 5 },
]

export default function BeansPage() {
  const [allBeans, setAllBeans] = useState<Bean[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [minScore, setMinScore] = useState(0)
  const [selectedBean, setSelectedBean] = useState<Bean | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getBeans({}, getToken())
      .then((items) => {
        if (!cancelled) setAllBeans(items)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '豆仓加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const beans = useMemo(() => {
    const q = query.trim().toLowerCase()
    return allBeans.filter((bean) => {
      if (minScore > 0 && (bean.avg_score == null || bean.avg_score < minScore)) return false
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
  }, [allBeans, query, minScore])

  const selectedRows = recommendedParamRows(selectedBean?.recommended_params)

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-dc-text-1">我的豆仓</h1>
        <Link href="/app/chat?new=bean" className="btn-primary text-sm flex items-center gap-1.5 px-4 py-2">
          <Plus size={14} /> 新建豆卡
        </Link>
      </div>

      <div className="mb-6 space-y-3">
        <div className="relative">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-dc-text-3" />
          <input
            className="dc-input pl-10 pr-9"
            placeholder="搜索烘焙商、庄园、豆种…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-dc-text-3 hover:text-dc-text-1"
            >
              <X size={14} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-dc-text-3 flex-shrink-0">评分</span>
          {SCORE_FILTERS.map((filter) => (
            <button
              key={filter.label}
              onClick={() => setMinScore(filter.min)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                minScore === filter.min
                  ? 'bg-dc-accent text-white border-dc-accent'
                  : 'border-dc-border text-dc-text-2 hover:border-dc-accent-hi bg-white'
              }`}
            >
              {filter.label}
            </button>
          ))}
          {beans.length < allBeans.length && (
            <span className="text-xs text-dc-text-3 ml-auto">
              {beans.length} / {allBeans.length} 款
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆仓…</div>
      ) : error ? (
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">豆仓暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      ) : beans.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有匹配的豆子</div>
          <p className="text-sm text-dc-text-3">可以换个关键词，或先新建一张豆卡。</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-3xl">
          {beans.map((bean) => (
            <BeanCard
              key={bean.bean_id}
              bean={bean}
              onNoParams={() => setSelectedBean(bean)}
            />
          ))}
        </div>
      )}

      {selectedBean && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setSelectedBean(null)}
        >
          <div
            className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-dc-text-1 mb-1">建议冲煮参数</h3>
            <p className="text-sm text-dc-text-3 mb-5 leading-relaxed">
              {selectedBean.name}
            </p>

            {selectedRows.length > 0 && (
              <div className="rounded-xl bg-dc-subtle border border-dc-border p-4 mb-4 grid grid-cols-2 gap-x-4 gap-y-2">
                {selectedRows.map(([key, value]) => (
                  <div key={key}>
                    <div className="text-xs text-dc-text-3 mb-0.5">{key}</div>
                    <div className="text-sm font-medium text-dc-text-1">{value}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-3">
              <RecommendParamsChat
                beanId={selectedBean.bean_id}
                hasParams={selectedRows.length > 0}
                onCompleted={(params, recordId) => {
                  const patch = { recommended_params: params, recommended_record_id: recordId, updated_at: new Date().toISOString() }
                  setAllBeans((current) =>
                    current.map((bean) => (bean.bean_id === selectedBean.bean_id ? { ...bean, ...patch } : bean)),
                  )
                  setSelectedBean((bean) => (bean ? { ...bean, ...patch } : bean))
                }}
              />
              <Link
                href={`/app/chat?new=1&bean_id=${encodeURIComponent(selectedBean.bean_id)}`}
                onClick={() => setSelectedBean(null)}
                className="dc-card p-4 flex items-center gap-3 hover:border-dc-accent-hi transition-colors block group"
              >
                <div className="w-8 h-8 rounded-lg bg-dc-accent-light flex items-center justify-center flex-shrink-0">
                  <ClipboardList size={14} className="text-dc-accent" strokeWidth={1.8} />
                </div>
                <div>
                  <div className="text-sm font-medium text-dc-text-1 group-hover:text-dc-accent transition-colors">
                    新增冲煮记录
                  </div>
                  <div className="text-xs text-dc-text-3 mt-0.5">记录会关联到当前豆卡</div>
                </div>
              </Link>
            </div>
            <button
              onClick={() => setSelectedBean(null)}
              className="mt-4 w-full text-sm text-dc-text-3 hover:text-dc-text-2 py-2 transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
