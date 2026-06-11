'use client'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { Search, Filter, X } from 'lucide-react'
import { getRecords } from '@/lib/api/records'
import { getToken } from '@/lib/auth'
import type { BrewRecord } from '@/types'

function ScoreChip({ score }: { score: number }) {
  const cls = score >= 5
    ? 'text-dc-green bg-dc-green-bg'
    : score >= 4
    ? 'text-dc-accent bg-dc-accent-light'
    : 'text-dc-text-2 bg-dc-subtle'
  return (
    <span className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${cls}`}>
      {score}
    </span>
  )
}

function isThisMonth(dateString: string) {
  const date = new Date(dateString)
  const now = new Date()
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()
}

function matchesQuery(record: BrewRecord, query: string) {
  if (!query.trim()) return true
  const needle = query.trim().toLowerCase()
  return [
    record.bean_name,
    record.origin,
    record.roaster,
    record.varietal,
    record.device,
    record.grinder,
    record.notes,
    record.raw_input,
  ].filter(Boolean).join(' ').toLowerCase().includes(needle)
}

export default function RecordsPage() {
  const [allRecords, setAllRecords] = useState<BrewRecord[]>([])
  const [bean, setBean] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [range, setRange] = useState<'all' | 'month'>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setBean(new URLSearchParams(window.location.search).get('bean'))
    const token = getToken()
    let cancelled = false
    setLoading(true)
    setError('')
    getRecords({ page_size: 100 }, token)
      .then((records) => {
        if (!cancelled) setAllRecords(records)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '冲煮记录加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const records = useMemo(() => {
    return allRecords.filter((record) => {
      if (bean && record.bean_name !== bean) return false
      if (range === 'month' && !isThisMonth(record.created_at)) return false
      return matchesQuery(record, query)
    })
  }, [allRecords, bean, query, range])

  const total = allRecords.length
  const monthly = allRecords.filter((record) => isThisMonth(record.created_at)).length
  const beanCount = new Set(allRecords.map(r => r.bean_name).filter(Boolean)).size

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-dc-text-1">冲煮记录</h1>
        <Link href="/app/chat?new=1" className="btn-primary text-sm flex items-center gap-1.5">
          + 新建记录
        </Link>
      </div>

      {/* Stats — single line */}
      <div className="flex items-baseline gap-1.5 mb-5 text-sm text-dc-text-3">
        <span className="text-xl font-extrabold text-dc-text-1">{total}</span>
        <span>次冲煮</span>
        <span className="mx-2 text-dc-border">·</span>
        <span className="text-xl font-extrabold text-dc-text-1">{monthly}</span>
        <span>本月</span>
        <span className="mx-2 text-dc-border">·</span>
        <span className="text-xl font-extrabold text-dc-text-1">{beanCount}</span>
        <span>款豆子</span>
      </div>

      {/* Active bean filter indicator */}
      {bean && (
        <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-dc-accent-light rounded-lg border border-dc-accent/20 w-fit">
          <span className="text-xs text-dc-accent font-medium">筛选：{bean}</span>
          <Link href="/app/records" className="text-dc-accent hover:opacity-70">
            <X size={13} />
          </Link>
        </div>
      )}

      {/* Search + filter */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-dc-text-3" />
          <input
            className="dc-input pl-9"
            placeholder="搜索豆名、备注…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <button className="btn-secondary flex items-center gap-2 px-4">
          <Filter size={14} />
          筛选
        </button>
      </div>

      {/* Filter chips (hidden when bean filter active) */}
      {!bean && (
        <div className="flex gap-2 mb-5 flex-wrap">
          {([['all', '全部'], ['month', '本月']] as ['all' | 'month', string][]).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setRange(value)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                range === value
                  ? 'bg-dc-accent text-white border-dc-accent'
                  : 'border-dc-border text-dc-text-2 hover:border-dc-accent-hi bg-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Table header (desktop) */}
      <div className="hidden md:grid grid-cols-[1fr_80px_120px_80px_80px_36px] gap-3 px-4 py-2 text-xs text-dc-text-3 border-b border-dc-border mb-1">
        <span>豆子</span>
        <span>器具</span>
        <span>参数</span>
        <span>水温</span>
        <span>评分</span>
        <span />
      </div>

      {/* Records */}
      {loading ? (
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载冲煮记录…</div>
      ) : error ? (
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">冲煮记录暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      ) : records.length === 0 ? (
        <div className="py-16 text-center text-sm text-dc-text-3">
          暂无{bean ? `「${bean}」的` : ''}冲煮记录
        </div>
      ) : (
        <div className="space-y-1.5">
          {records.map(r => {
            const score = r.evaluation?.overall?.score
            const date = r.created_at.slice(0, 10)
            const params = [
              r.dose_g !== undefined ? `${r.dose_g}g` : null,
              r.water_ml !== undefined ? `${r.water_ml}ml` : null,
              r.ratio,
            ].filter(Boolean).join(' / ')

            const meta = [date, r.origin, r.grinder, r.device].filter(Boolean).join(' · ')

            return (
              <Link
                key={r.id}
                href={`/app/records/${r.id}`}
                className="dc-card flex items-center gap-3 px-4 py-3.5 hover:border-dc-accent-hi transition-colors block"
              >
                {score !== undefined && <ScoreChip score={score} />}
                <div className="flex-1 min-w-0 md:grid md:grid-cols-[1fr_80px_120px_80px_36px] md:gap-3 md:items-center">
                  <div>
                    <div className="text-sm font-medium text-dc-text-1 truncate">{r.bean_name ?? '未命名'}</div>
                    <div className="text-xs text-dc-text-3 mt-0.5 truncate">{meta}</div>
                  </div>
                  <span className="hidden md:block dc-tag text-center">{r.device}</span>
                  <span className="hidden md:block text-xs text-dc-text-2">{params}</span>
                  <span className="hidden md:block text-xs text-dc-text-2">{r.water_temp_c !== undefined ? `${r.water_temp_c}°C` : ''}</span>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
