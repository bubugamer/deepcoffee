'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Search, ChevronRight } from 'lucide-react'
import { getArticles, getKbFilterCategories } from '@/lib/api/knowledge'
import { ApiError } from '@/lib/api/client'
import { getToken } from '@/lib/auth'
import type { Article } from '@/types'

function groupByCategory(articles: Article[]): { cat: string; items: Article[] }[] {
  const map = new Map<string, Article[]>()
  for (const a of articles) {
    if (!map.has(a.cat)) map.set(a.cat, [])
    map.get(a.cat)!.push(a)
  }
  return Array.from(map.entries()).map(([cat, items]) => ({ cat, items }))
}

export default function KnowledgePage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [filterCategories, setFilterCategories] = useState<string[]>(['全部'])
  const [activeCategory, setActiveCategory] = useState('全部')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [upgrade, setUpgrade] = useState(false)

  useEffect(() => {
    const token = getToken()
    let cancelled = false
    setLoading(true)
    setError('')
    setUpgrade(false)
    Promise.all([getArticles(undefined, undefined, token), getKbFilterCategories(token)])
      .then(([nextArticles, nextFilterCategories]) => {
        if (cancelled) return
        setArticles(nextArticles)
        setFilterCategories(nextFilterCategories)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 403) {
          setUpgrade(true)
          return
        }
        setError(err instanceof Error ? err.message : '知识库加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  // 分类标签与文章的 cat 字段同源（都是后端 CATEGORY_LABELS 的 label），故客户端按 cat 筛选即可。
  const visibleArticles = activeCategory === '全部'
    ? articles
    : articles.filter((a) => a.cat === activeCategory)
  const groups = groupByCategory(visibleArticles)

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <h1 className="text-xl font-bold text-dc-text-1 mb-6">知识库</h1>

      {upgrade ? (
        <div className="dc-card p-6 max-w-lg">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">升级 Max 后可自由浏览知识库</div>
          <p className="text-sm text-dc-text-3 mb-4">你仍然可以在 Deepcoffee AI 中提问，并打开 AI 回答中引用过的文章。</p>
          <Link href="/app/settings?tab=plan" className="btn-primary text-sm px-4 py-2 inline-flex">查看会员权益</Link>
        </div>
      ) : (
        <>
          <div className="relative mb-5">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-dc-text-3" />
            <input
              className="dc-input pl-10"
              placeholder="搜索文章，如「冲煮建议」「涩感」「瑰夏」…"
            />
          </div>

          <div className="flex gap-2 flex-wrap mb-6">
            {filterCategories.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setActiveCategory(c)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  c === activeCategory
                    ? 'bg-dc-accent text-white border-dc-accent'
                    : 'border-dc-border text-dc-text-2 bg-white hover:border-dc-accent-hi'
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="dc-card p-6 text-sm text-dc-text-3">正在加载知识库…</div>
          ) : error ? (
            <div className="dc-card p-6">
              <div className="text-sm font-semibold text-dc-text-1 mb-1">知识库暂时不可用</div>
              <p className="text-sm text-dc-text-3">{error}</p>
            </div>
          ) : groups.length === 0 ? (
            <div className="dc-card p-8 text-center text-sm text-dc-text-3">知识库暂时没有可浏览的文章</div>
          ) : (
            <div className="space-y-6">
              {groups.map(({ cat, items }) => (
                <div key={cat}>
                  <div className="text-xs font-semibold text-dc-text-3 uppercase tracking-wide mb-2 px-1">
                    {cat}
                  </div>
                  <div className="dc-card divide-y divide-dc-border overflow-hidden">
                    {items.map(a => (
                      <Link
                        key={a.slug}
                        href={`/knowledge/${a.slug}`}
                        className="flex items-center gap-3 px-4 py-3.5 hover:bg-dc-subtle transition-colors group"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-sm font-medium text-dc-text-1 group-hover:text-dc-accent transition-colors">
                              {a.title}
                            </span>
                          </div>
                          <p className="text-xs text-dc-text-3 line-clamp-1">{a.desc}</p>
                        </div>
                        <ChevronRight size={14} className="text-dc-text-3 flex-shrink-0 group-hover:text-dc-accent transition-colors" />
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
