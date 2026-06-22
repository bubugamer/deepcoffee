'use client'
import Link from 'next/link'
import { useEffect, useState, type ElementType } from 'react'
import { ArrowRight, Plus, Search, Coffee, BookOpen, DropletIcon, Settings2 } from 'lucide-react'
import { getRecords } from '@/lib/api/records'
import { getKbCategories } from '@/lib/api/knowledge'
import { getToken } from '@/lib/auth'
import { useProfile } from '@/components/ProfileContext'
import { canBrowseKnowledge } from '@/lib/entitlements'
import type { BrewRecord, KBCategory } from '@/types'

// 按用户时区的当前小时取问候语；拿不到时区就退回浏览器本地时区。
function greetingFor(timezone?: string | null): string {
  let hour = new Date().getHours()
  try {
    const tz = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', hourCycle: 'h23' }).formatToParts(new Date())
    const parsed = parseInt(parts.find((p) => p.type === 'hour')?.value ?? '', 10)
    if (!Number.isNaN(parsed)) hour = parsed
  } catch {
    /* 无效时区等异常时用浏览器本地小时 */
  }
  if (hour < 5) return '夜深了'
  if (hour < 11) return '早安'
  if (hour < 13) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

const iconMap: Record<string, ElementType> = {
  origin: Coffee,
  varietal: BookOpen,
  process: DropletIcon,
  equipment: Settings2,
}

function ScoreDot({ score }: { score: number }) {
  const color = score >= 5
    ? 'text-dc-green bg-dc-green-bg'
    : score >= 4
    ? 'text-dc-accent bg-dc-accent-light'
    : 'text-dc-text-2 bg-dc-subtle'
  return (
    <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${color}`}>
      {score}
    </div>
  )
}

export default function DashboardPage() {
  const { profile } = useProfile()
  const canViewKnowledge = canBrowseKnowledge(profile)
  const greeting = greetingFor(profile?.timezone)
  const [recentBrews, setRecentBrews] = useState<BrewRecord[]>([])
  const [categories, setCategories] = useState<KBCategory[]>([])
  const [loading, setLoading] = useState(true)
  const [recordsError, setRecordsError] = useState('')
  const [knowledgeError, setKnowledgeError] = useState('')

  useEffect(() => {
    const token = getToken()
    let cancelled = false
    setLoading(true)
    setRecordsError('')
    setKnowledgeError('')

    Promise.allSettled([
      getRecords({ page_size: 3 }, token),
      canViewKnowledge ? getKbCategories() : Promise.resolve([]),
    ]).then(([recordsResult, categoriesResult]) => {
      if (cancelled) return
      if (recordsResult.status === 'fulfilled') {
        setRecentBrews(recordsResult.value.slice(0, 3))
      } else {
        setRecordsError(recordsResult.reason instanceof Error ? recordsResult.reason.message : '冲煮记录加载失败')
      }
      if (categoriesResult.status === 'fulfilled') {
        setCategories(categoriesResult.value)
      } else {
        setKnowledgeError(categoriesResult.reason instanceof Error ? categoriesResult.reason.message : '知识库加载失败')
      }
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })

    return () => { cancelled = true }
  }, [canViewKnowledge])

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      {/* Greeting */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-dc-text-1 mb-1">{greeting}</h1>
        <p className="text-sm text-dc-text-2">今天冲了什么？</p>
      </div>

      {/* Quick input */}
      <Link
        href="/app/chat?new=1"
        className="block dc-card p-5 mb-8 hover:border-dc-accent-hi transition-colors group"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="text-sm text-dc-text-3 flex-1">随便描述这次冲煮…</div>
          <ArrowRight size={16} className="text-dc-text-3 group-hover:text-dc-accent transition-colors" />
        </div>
        <div className="flex gap-2 flex-wrap">
          <span className="dc-tag flex items-center gap-1 cursor-pointer hover:bg-dc-accent-light hover:text-dc-accent transition-colors">
            <Plus size={11} /> 新建记录
          </span>
          <span className="dc-tag flex items-center gap-1 cursor-pointer hover:bg-dc-accent-light hover:text-dc-accent transition-colors">
            <Search size={11} /> 问知识库
          </span>
        </div>
      </Link>

      {/* Recent brews */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="section-title">最近冲煮</h2>
          <Link href="/app/records" className="text-xs text-dc-accent hover:underline flex items-center gap-1">
            全部记录 <ArrowRight size={12} />
          </Link>
        </div>
        {loading ? (
          <div className="dc-card p-4 text-sm text-dc-text-3">正在加载最近冲煮…</div>
        ) : recordsError ? (
          <div className="dc-card p-4">
            <div className="text-sm font-semibold text-dc-text-1 mb-1">最近冲煮暂时不可用</div>
            <p className="text-sm text-dc-text-3">{recordsError}</p>
          </div>
        ) : recentBrews.length === 0 ? (
          <div className="dc-card p-6 text-center text-sm text-dc-text-3">暂无冲煮记录</div>
        ) : (
          <div className="space-y-3">
            {recentBrews.map(b => {
              const score = b.brew_score ?? undefined
              const date = b.created_at.slice(0, 10)
              return (
                <Link
                  key={b.id}
                  href={`/app/records/${b.id}`}
                  className="dc-card p-4 flex gap-4 hover:border-dc-accent-hi transition-colors block"
                >
                  {score !== undefined && <ScoreDot score={score} />}
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-sm text-dc-text-1 mb-0.5 truncate">{b.bean_name ?? '未命名'}</div>
                    <div className="text-xs text-dc-text-3 mb-2">{date} · {b.origin ?? '未标注产地'}</div>
                    <div className="flex gap-1.5 flex-wrap">
                      {[
                        b.device,
                        b.grinder && b.grind_setting ? `${b.grinder} ${b.grind_setting}` : b.grinder,
                        b.dose_g !== undefined && b.water_ml !== undefined ? `${b.dose_g}g / ${b.water_ml}ml` : undefined,
                        b.water_temp_c !== undefined ? `${b.water_temp_c}°C` : undefined,
                      ].filter(Boolean).map(t => (
                        <span key={t} className="dc-tag">{t}</span>
                      ))}
                    </div>
                    {b.notes && <p className="text-xs text-dc-text-2 mt-2 line-clamp-1">{b.notes}</p>}
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </div>

      {canViewKnowledge && (
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="section-title">知识库</h2>
          <Link href="/knowledge" className="text-xs text-dc-accent hover:underline flex items-center gap-1">
            浏览全部 <ArrowRight size={12} />
          </Link>
        </div>
        {loading ? (
          <div className="dc-card p-4 text-sm text-dc-text-3">正在加载知识库…</div>
        ) : knowledgeError ? (
          <div className="dc-card p-4">
            <div className="text-sm font-semibold text-dc-text-1 mb-1">知识库暂时不可用</div>
            <p className="text-sm text-dc-text-3">{knowledgeError}</p>
          </div>
        ) : categories.length === 0 ? (
          <div className="dc-card p-6 text-center text-sm text-dc-text-3">知识库分类暂时为空</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {categories.map(({ key, label, sub, href }) => {
              const Icon = iconMap[key] ?? BookOpen
              return (
                <Link
                  key={key}
                  href={href || `/knowledge?cat=${key}`}
                  className="dc-card p-4 hover:border-dc-accent-hi transition-colors block"
                >
                  <div className="w-9 h-9 rounded-xl bg-dc-accent-light flex items-center justify-center mb-3">
                    <Icon size={17} className="text-dc-accent" strokeWidth={1.8} />
                  </div>
                  <div className="text-sm font-semibold text-dc-text-1 mb-0.5">{label}</div>
                  <div className="text-xs text-dc-text-3">{sub}</div>
                </Link>
              )
            })}
          </div>
        )}
      </div>
      )}
    </div>
  )
}
