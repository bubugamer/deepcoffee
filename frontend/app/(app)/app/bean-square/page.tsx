'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { Check, Eye, Loader2, Plus, Search, X } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
import { getBeanSquare, importBeanSquare } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'
import { recommendedParamRows } from '@/lib/beans'
import type { BeanSquareImportResponse, BeanSquareItem } from '@/types'

interface CardTheme {
  bg: string
  textMain: string
  textSub: string
  accent: string
  tagBg: string
}

function getTheme(process?: string | null): CardTheme {
  const p = process ?? ''
  if (p.includes('CM') || p.includes('厌氧')) {
    return { bg: 'linear-gradient(145deg, #EAF5EE 0%, #D6EDD9 100%)', textMain: '#1A3D28', textSub: '#4A7258', accent: '#2D6B42', tagBg: '#B8DEC0' }
  }
  if (p.includes('水洗')) {
    return { bg: 'linear-gradient(145deg, #EBF3FA 0%, #D5E8F5 100%)', textMain: '#12304A', textSub: '#3A6280', accent: '#2054A0', tagBg: '#B8D4EA' }
  }
  if (p.includes('日晒')) {
    return { bg: 'linear-gradient(145deg, #FEF4EC 0%, #FAE4CC 100%)', textMain: '#4A1A00', textSub: '#8A4820', accent: '#9B5E1A', tagBg: '#F2C89A' }
  }
  if (p.includes('蜜')) {
    return { bg: 'linear-gradient(145deg, #FFFAEC 0%, #FDF0C8 100%)', textMain: '#4A3000', textSub: '#8A6820', accent: '#8B6A14', tagBg: '#F5DA80' }
  }
  return { bg: 'linear-gradient(145deg, #FBF5EF 0%, #F2E6D8 100%)', textMain: '#3A1E0A', textSub: '#7A5038', accent: '#9B5E1A', tagBg: '#E5C8A8' }
}

function beanSearchText(bean: BeanSquareItem) {
  return [
    bean.name,
    bean.roaster,
    bean.roaster_product,
    bean.coffee_source,
    bean.green_bean_merchant,
    bean.green_bean_product,
    bean.origin,
    bean.process,
    bean.public_comment,
    ...bean.varietal,
    ...bean.flavor.notes,
  ].filter(Boolean).join(' ').toLowerCase()
}

function formatDate(value?: string | null) {
  if (!value) return null
  return value.slice(0, 10)
}

function SquareCard({
  bean,
  selected,
  onToggle,
  onInspect,
}: {
  bean: BeanSquareItem
  selected: boolean
  onToggle: () => void
  onInspect: () => void
}) {
  const theme = getTheme(bean.process)
  const varietal = bean.varietal.length ? bean.varietal.join(' / ') : undefined
  const notes = bean.flavor.notes.slice(0, 4)
  const score = bean.rating?.overall?.score ?? bean.avg_score

  return (
    <article
      className={`relative min-h-[300px] rounded-2xl p-5 flex flex-col border transition-all ${
        selected ? 'border-dc-accent shadow-sm' : 'border-transparent'
      }`}
      style={{ background: theme.bg }}
    >
      <div className="flex items-start justify-between gap-3 mb-auto">
        <span className="text-xs font-medium truncate" style={{ color: theme.textSub }}>
          {bean.roaster ?? '匿名豆卡'}
        </span>
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={selected}
          className="w-8 h-8 rounded-full flex items-center justify-center border transition-colors"
          style={{
            borderColor: selected ? theme.accent : theme.tagBg,
            background: selected ? theme.accent : 'rgba(255,255,255,0.45)',
            color: selected ? '#fff' : theme.textMain,
          }}
        >
          <Check size={15} />
        </button>
      </div>

      <div className="py-5">
        <h3 className="text-xl font-bold leading-snug line-clamp-3" style={{ color: theme.textMain }}>
          {bean.name}
        </h3>
      </div>

      {notes.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {notes.map((note) => (
            <span key={note} className="text-xs px-2 py-0.5 rounded-full" style={{ background: theme.tagBg, color: theme.textMain }}>
              {note}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-end justify-between gap-3">
        <div className="flex flex-col gap-1.5 min-w-0">
          {bean.origin && <span className="text-xs truncate" style={{ color: theme.textSub }}>{bean.origin}</span>}
          {varietal && <span className="text-xs truncate" style={{ color: theme.textSub }}>{varietal}</span>}
          {bean.process && (
            <span className="text-xs px-2 py-0.5 rounded-full font-medium w-fit" style={{ background: theme.tagBg, color: theme.accent }}>
              {bean.process}
            </span>
          )}
        </div>
        {score !== null && score !== undefined && (
          <div className="text-right flex-shrink-0">
            <div className="text-3xl font-black leading-none" style={{ color: theme.accent }}>{score}</div>
            <div className="text-xs mt-0.5" style={{ color: theme.textSub }}>/5</div>
          </div>
        )}
      </div>

      {bean.public_comment && (
        <p className="mt-4 text-xs leading-relaxed line-clamp-2" style={{ color: theme.textSub }}>
          匿名评论：{bean.public_comment}
        </p>
      )}

      <button
        type="button"
        onClick={onInspect}
        className="mt-4 flex items-center justify-center gap-1 text-xs font-medium py-1.5 rounded-full transition-opacity hover:opacity-75"
        style={{ background: theme.tagBg, color: theme.textMain }}
      >
        <Eye size={12} />
        查看详情
      </button>
    </article>
  )
}

function DetailModal({ bean, onClose }: { bean: BeanSquareItem; onClose: () => void }) {
  const rows = recommendedParamRows(bean.recommended_params)
  const details = [
    ['烘焙商', bean.roaster],
    ['产地', bean.origin],
    ['处理法', bean.process],
    ['品种', bean.varietal.join(' / ') || null],
    ['海拔', bean.altitude_text],
    ['采收期', bean.harvest_date_text],
    ['烘焙日期', bean.roast_date_text],
    ['净重', bean.net_weight_text],
  ].filter(([, value]) => value)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4" onClick={onClose}>
      <div className="dc-card w-full max-w-2xl max-h-[86vh] overflow-y-auto p-5" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 mb-5">
          <div>
            <h2 className="text-lg font-bold text-dc-text-1">{bean.name}</h2>
            <p className="text-xs text-dc-text-3 mt-1">匿名豆卡 · {formatDate(bean.updated_at)}</p>
          </div>
          <button onClick={onClose} className="p-1 text-dc-text-3 hover:text-dc-text-1">
            <X size={18} />
          </button>
        </div>

        <div className="grid sm:grid-cols-2 gap-3 mb-5">
          {details.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-dc-subtle border border-dc-border p-3">
              <div className="text-[11px] text-dc-text-3 mb-1">{label}</div>
              <div className="text-sm font-medium text-dc-text-1">{value}</div>
            </div>
          ))}
        </div>

        {bean.flavor.notes.length > 0 && (
          <div className="mb-5">
            <div className="text-xs font-semibold text-dc-text-2 mb-2">风味信息</div>
            <div className="flex flex-wrap gap-1.5">
              {bean.flavor.notes.map((note) => (
                <span key={note} className="dc-tag-accent">{note}</span>
              ))}
            </div>
          </div>
        )}

        {rows.length > 0 && (
          <div className="mb-5">
            <div className="text-xs font-semibold text-dc-text-2 mb-2">建议冲煮参数</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {rows.map(([label, value]) => (
                <div key={label} className="rounded-lg bg-dc-subtle border border-dc-border p-3">
                  <div className="text-[11px] text-dc-text-3 mb-1">{label}</div>
                  <div className="text-sm font-medium text-dc-text-1">{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {bean.bean_components.length > 0 && (
          <div className="mb-5">
            <div className="text-xs font-semibold text-dc-text-2 mb-2">豆源组成</div>
            <div className="space-y-2">
              {bean.bean_components.map((component, index) => (
                <div key={index} className="rounded-lg bg-dc-subtle border border-dc-border p-3 text-sm text-dc-text-2">
                  {[component.origin_name, component.coffee_source_name, component.process_name, component.varietal_names.join(' / '), component.share_text]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              ))}
            </div>
          </div>
        )}

        {bean.public_comment && (
          <div className="rounded-lg bg-dc-accent-light border border-dc-accent/20 p-4">
            <div className="text-xs font-semibold text-dc-accent mb-1">匿名评论</div>
            <p className="text-sm leading-relaxed text-dc-text-2">{bean.public_comment}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function BeanSquarePage() {
  const [allBeans, setAllBeans] = useState<BeanSquareItem[]>([])
  const [query, setQuery] = useState('')
  const [process, setProcess] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [detailBean, setDetailBean] = useState<BeanSquareItem | null>(null)
  const [result, setResult] = useState<BeanSquareImportResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [upgradeRequired, setUpgradeRequired] = useState(false)

  useEffect(() => {
    let cancelled = false
    const token = getToken()
    setLoading(true)
    setError('')
    setUpgradeRequired(false)
    getBeanSquare({}, token)
      .then((items) => {
        if (!cancelled) setAllBeans(items)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 403) {
          setUpgradeRequired(true)
          return
        }
        setError(err instanceof Error ? err.message : '豆仓广场加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const processOptions = useMemo(() => {
    return Array.from(new Set(allBeans.map((bean) => bean.process).filter((value): value is string => Boolean(value)))).sort()
  }, [allBeans])

  const beans = useMemo(() => {
    const q = query.trim().toLowerCase()
    return allBeans.filter((bean) => {
      if (process && bean.process !== process) return false
      if (!q) return true
      return beanSearchText(bean).includes(q)
    })
  }, [allBeans, process, query])

  const selectedCount = selectedIds.size

  function toggleBean(beanId: string) {
    setResult(null)
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(beanId)) next.delete(beanId)
      else next.add(beanId)
      return next
    })
  }

  async function handleImport() {
    if (selectedIds.size === 0) return
    setImporting(true)
    setError('')
    setResult(null)
    try {
      const response = await importBeanSquare(Array.from(selectedIds), getToken())
      setResult(response)
      setSelectedIds(new Set())
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setUpgradeRequired(true)
      } else {
        setError(err instanceof Error ? err.message : '加入我的豆仓失败，请稍后重试。')
      }
    } finally {
      setImporting(false)
    }
  }

  if (upgradeRequired) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <div className="dc-card p-6 max-w-lg">
          <h1 className="text-lg font-bold text-dc-text-1 mb-2">升级后可进入豆仓广场</h1>
          <p className="text-sm text-dc-text-3 leading-relaxed mb-5">
            Pro 或 Max 用户可以查看匿名豆卡信息，并把选中的豆卡加入自己的豆仓。
          </p>
          <Link href="/app/settings" className="btn-primary inline-flex">查看会员方案</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-bold text-dc-text-1">豆仓广场</h1>
          <p className="text-xs text-dc-text-3 mt-1">匿名豆卡信息与公开评论，不展示个人身份和备注。</p>
        </div>
        <button
          type="button"
          disabled={selectedCount === 0 || importing}
          onClick={handleImport}
          className="btn-primary flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {importing ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          加入我的豆仓{selectedCount > 0 ? `（${selectedCount}）` : ''}
        </button>
      </div>

      <div className="mb-5 space-y-3">
        <div className="relative">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-dc-text-3" />
          <input
            className="dc-input pl-10 pr-9"
            placeholder="搜索豆名、烘焙商、产地、处理法、评论…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-dc-text-3 hover:text-dc-text-1"
            >
              <X size={14} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 overflow-x-auto no-scroll pb-1">
          <span className="text-xs text-dc-text-3 flex-shrink-0">处理法</span>
          <button
            type="button"
            onClick={() => setProcess('')}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors flex-shrink-0 ${
              process === '' ? 'bg-dc-accent text-white border-dc-accent' : 'border-dc-border text-dc-text-2 hover:border-dc-accent-hi bg-white'
            }`}
          >
            全部
          </button>
          {processOptions.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setProcess(option)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors flex-shrink-0 ${
                process === option ? 'bg-dc-accent text-white border-dc-accent' : 'border-dc-border text-dc-text-2 hover:border-dc-accent-hi bg-white'
              }`}
            >
              {option}
            </button>
          ))}
          {beans.length < allBeans.length && (
            <span className="text-xs text-dc-text-3 ml-auto flex-shrink-0">{beans.length} / {allBeans.length} 款</span>
          )}
        </div>
      </div>

      {result && (
        <div className="dc-card p-4 mb-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="text-sm text-dc-text-2">
            已加入 {result.created_count} 款，已有 {result.existing_count} 款。
          </div>
          <Link href="/app/beans" className="btn-secondary text-sm inline-flex justify-center">前往我的豆仓</Link>
        </div>
      )}

      {error && (
        <div className="dc-card p-4 mb-5">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">操作未完成</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆仓广场…</div>
      ) : beans.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有匹配的豆卡</div>
          <p className="text-sm text-dc-text-3">可以换个关键词或处理法。</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {beans.map((bean) => (
            <SquareCard
              key={bean.bean_id}
              bean={bean}
              selected={selectedIds.has(bean.bean_id)}
              onToggle={() => toggleBean(bean.bean_id)}
              onInspect={() => setDetailBean(bean)}
            />
          ))}
        </div>
      )}

      {detailBean && <DetailModal bean={detailBean} onClose={() => setDetailBean(null)} />}
    </div>
  )
}
