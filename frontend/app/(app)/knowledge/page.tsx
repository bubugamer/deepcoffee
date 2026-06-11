import Link from 'next/link'
import { Search, ChevronRight } from 'lucide-react'
import { getArticles, getKbFilterCategories } from '@/lib/api/knowledge'
import type { Article } from '@/types'

// Server Component 默认会在 docker build 阶段被静态预渲染，而构建容器里连不上 api，
// 「fetch failed」会被烤进静态 HTML。声明为按请求动态渲染，SSR 时走 API_INTERNAL_URL。
export const dynamic = 'force-dynamic'

function groupByCategory(articles: Article[]): { cat: string; items: Article[] }[] {
  const map = new Map<string, Article[]>()
  for (const a of articles) {
    if (!map.has(a.cat)) map.set(a.cat, [])
    map.get(a.cat)!.push(a)
  }
  return Array.from(map.entries()).map(([cat, items]) => ({ cat, items }))
}

export default async function KnowledgePage() {
  let articles: Article[] = []
  let filterCategories: string[] = ['全部']
  let error = ''

  try {
    const [nextArticles, nextFilterCategories] = await Promise.all([
      getArticles(),
      getKbFilterCategories(),
    ])
    articles = nextArticles
    filterCategories = nextFilterCategories
  } catch (err) {
    error = err instanceof Error ? err.message : '知识库加载失败，请稍后重试。'
  }

  const groups = groupByCategory(articles)

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      {/* Header */}
      <h1 className="text-xl font-bold text-dc-text-1 mb-6">知识库</h1>

      {/* Search */}
      <div className="relative mb-5">
        <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-dc-text-3" />
        <input
          className="dc-input pl-10"
          placeholder="搜索文章，如「冲煮建议」「涩感」「瑰夏」…"
        />
      </div>

      {/* Category filter */}
      <div className="flex gap-2 flex-wrap mb-6">
        {filterCategories.map((c, i) => (
          <button
            key={c}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              i === 0
                ? 'bg-dc-accent text-white border-dc-accent'
                : 'border-dc-border text-dc-text-2 bg-white hover:border-dc-accent-hi'
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {error ? (
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
    </div>
  )
}
