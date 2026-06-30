'use client'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { ClipboardList, ExternalLink, Plus, Search, X } from 'lucide-react'
import { getBeans } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { getCardTheme, flavorEmoji, recommendedParamRows, RATING_LABELS } from '@/lib/beans'
import type { Bean } from '@/types'

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
  const href = `/app/records?bean=${encodeURIComponent(bean.name)}&bean_id=${encodeURIComponent(bean.bean_id)}`
  return (
    <Link
      href={href}
      onClick={(event) => event.stopPropagation()}
      className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-opacity hover:opacity-70"
      style={{ background: bgColor, color: textColor }}
    >
      <ClipboardList size={11} />
      冲煮记录
    </Link>
  )
}

function BeanDetailBtn({ bean, textColor, bgColor }: { bean: Bean; textColor: string; bgColor: string }) {
  return (
    <Link
      href={`/app/beans/${bean.bean_id}`}
      onClick={(event) => event.stopPropagation()}
      className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-opacity hover:opacity-70"
      style={{ background: bgColor, color: textColor }}
    >
      <ExternalLink size={11} />
      豆卡详情
    </Link>
  )
}

function BeanCard({ bean }: { bean: Bean }) {
  const [flipped, setFlipped] = useState(false)
  const isBlend = bean.bean_product_type === 'blend'
  const theme = getCardTheme(bean.process || bean.bean_components?.[0]?.process_name, { blend: isBlend })
  const flavor = bean.flavor
  const notes = flavor?.notes ?? []
  const axes = flavor?.axes ?? []
  const paramRows = recommendedParamRows(bean.recommended_params)
  const beanScore = bean.rating?.overall?.score ?? bean.avg_score
  // 正面三属性（产地/品种/处理法）按豆源出列：拼配多列、单豆 1 列；样式统一为纯文字。
  const sourceColumns = (bean.bean_components?.length
    ? bean.bean_components.map((c) => ({
        origin: c.origin_name ?? undefined,
        varietal: c.varietal_names?.length ? c.varietal_names.join(' / ') : undefined,
        process: c.process_name ?? undefined,
      }))
    : [{
        origin: bean.origin ?? undefined,
        varietal: bean.varietal.length ? bean.varietal.join(' / ') : undefined,
        process: bean.process ?? undefined,
      }]
  ).filter((col) => col.origin || col.varietal || col.process)
  // 风味强度为空时，用评分维度作「用户评价」展示。
  const ratingRows = RATING_LABELS
    .map(([key, label]) => ({ label, score: bean.rating?.[key]?.score }))
    .filter((r) => r.score !== undefined && r.score !== null)

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
            <BeanDetailBtn bean={bean} textColor={theme.textMain} bgColor={theme.tagBg} />
          </div>

          <div className="flex-1 flex items-center py-3">
            <h3 className="text-xl font-bold leading-snug line-clamp-3" style={{ color: theme.textMain }}>
              {bean.name}
            </h3>
          </div>

          {notes.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {notes.map((note) => {
                const emoji = flavorEmoji(note, flavor?.note_emojis)
                return (
                  <span
                    key={note}
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: theme.tagBg, color: theme.textMain }}
                  >
                    {emoji ? `${emoji} ${note}` : note}
                  </span>
                )
              })}
            </div>
          )}

          <div className="flex items-end justify-between gap-3">
            <div className="flex gap-4 min-w-0 overflow-hidden">
              {sourceColumns.slice(0, 3).map((col, index) => (
                <div key={index} className="flex flex-col gap-1.5 min-w-0">
                  {col.origin && <span className="text-xs truncate" style={{ color: theme.textSub }}>{col.origin}</span>}
                  {col.varietal && <span className="text-xs truncate" style={{ color: theme.textSub }}>{col.varietal}</span>}
                  {col.process && <span className="text-xs truncate" style={{ color: theme.textSub }}>{col.process}</span>}
                </div>
              ))}
            </div>
            {beanScore !== null && beanScore !== undefined && (
              <div className="text-right flex-shrink-0">
                <div className="text-3xl font-black leading-none" style={{ color: theme.accent }}>
                  {beanScore}
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
            <BrewRecordsBtn bean={bean} textColor={theme.textMain} bgColor={theme.tagBg} />
          </div>

          <div style={{ height: 1, background: theme.tagBg, flexShrink: 0 }} />

          <div className="flex-1 overflow-hidden">
            <p className="text-xs font-semibold mb-2" style={{ color: theme.accent }}>
              {axes.length > 0 ? '风味强度' : ratingRows.length > 0 ? '用户评价' : '风味强度'}
            </p>
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
            ) : ratingRows.length > 0 ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {ratingRows.map(({ label, score }) => (
                  <div key={label} className="flex items-center gap-2">
                    <span className="text-xs flex-shrink-0 truncate" style={{ color: theme.textSub, width: '3.5em' }}>
                      {label}
                    </span>
                    <Dots value={score} max={5} color={theme.accent} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs leading-relaxed" style={{ color: theme.textSub }}>暂无评价</p>
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
      const beanScore = bean.rating?.overall?.score ?? bean.avg_score
      if (minScore > 0 && (beanScore == null || beanScore < minScore)) return false
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

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-dc-text-1">我的豆仓</h1>
        <Link href="/app/beans/new" className="btn-primary text-sm flex items-center gap-1.5 px-4 py-2">
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
            <BeanCard key={bean.bean_id} bean={bean} />
          ))}
        </div>
      )}
    </div>
  )
}
