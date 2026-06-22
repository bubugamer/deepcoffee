import type { Article, ArticleDetail, ArticleSection, KBCategory } from '@/types'
import { ApiError, apiFetch, isApiEnabled } from './client'

// Local fallback for development when NEXT_PUBLIC_API_BASE_URL is not configured.
const fallbackKbCategories: KBCategory[] = [
  { key: 'guides',     label: '冲煮指南', count: 5, sub: '冲煮建议、参数调整、风味排查…', href: '/knowledge?cat=guides' },
  { key: 'origins',    label: '产区',     count: 1, sub: '产区风味地图', href: '/knowledge?cat=origins' },
  { key: 'varietals',  label: '品种',     count: 1, sub: '品种与处理法风味图谱', href: '/knowledge?cat=varietals' },
  { key: 'processing', label: '处理法',   count: 1, sub: '处理法概览', href: '/knowledge?cat=processing' },
]

const fallbackKbFilterCategories: string[] = [
  '全部', '冲煮指南', '产区', '品种', '处理法', '器具',
]

const fallbackArticles: Article[] = [
  { slug: 'guides__如何获得冲煮建议', cat: '冲煮指南', title: '如何获得更准确的冲煮建议', desc: '确认豆子、器具、研磨、参数和杯中问题后，再给可执行的起手方案。' },
  { slug: 'guides__手冲参数调整指南', cat: '冲煮指南', title: '手冲参数调整指南', desc: '酸、苦、涩、薄、闷时，下一杯优先改研磨、比例、水温还是搅拌。' },
  { slug: 'guides__常见风味问题排查', cat: '冲煮指南', title: '常见风味问题排查', desc: '把不好喝拆成可判断的问题，再按单变量调整下一杯。' },
  { slug: 'origins__产区风味地图', cat: '产区', title: '产区风味地图', desc: '用国家、子产区、来源主体、品种和处理法一起建立风味预期。' },
  { slug: 'varietals__品种与处理法风味图谱', cat: '品种', title: '品种与处理法风味图谱', desc: '理解品种和处理法如何共同影响花香、果香、甜感和发酵感。' },
  { slug: 'processing__处理法概览', cat: '处理法', title: '处理法概览', desc: '水洗、日晒、蜜处理、厌氧、CM 和共发酵的差异。' },
]

const fallbackArticleDetails: Record<string, { article: Article; body: ArticleSection[] }> = {
  geisha: {
    article: {
      slug: 'geisha', cat: '品种', title: '瑰夏 Geisha',
      desc: '茉莉花香与柑橘风味，翡翠庄园 2004 年将其带入世界视野，BOP 拍卖历年高价纪录保持者。',
      updated: '2026-05-20',
      toc: [
        { id: '起源',     title: '起源',     level: 2 },
        { id: '爆火契机', title: '爆火契机', level: 2 },
        { id: '风味特征', title: '风味特征', level: 2 },
        { id: '冲煮建议', title: '冲煮建议', level: 2 },
      ],
      related: [
        { slug: 'process',   title: '处理法概览' },
        { slug: 'c40',       title: 'Comandante C40' },
        { slug: 'nicaragua', title: '尼加拉瓜' },
      ],
    },
    body: [
      {
        id: '起源', heading: '起源',
        body: '瑰夏是目前精品咖啡界最受关注的品种，以茉莉花香和柑橘风味著称，辨识度极高。原产于埃塞俄比亚 Gesha 村附近的野生咖啡林，1931 年被英国探险家发现并带出非洲，辗转传至哥斯达黎加，后进入巴拿马。',
      },
      {
        id: '爆火契机', heading: '爆火契机',
        body: '2004 年，巴拿马翡翠庄园（Hacienda La Esmeralda）在 BOP（Best of Panama）竞赛中凭借瑰夏一鸣惊人，拍出当时令人瞠目的高价，开创了精品豆拍卖的新纪元。此后每年 BOP 拍卖均由翡翠庄园的瑰夏主导，价格屡创新高。',
      },
      {
        id: '风味特征', heading: '风味特征',
        items: [
          '水洗：茉莉花香、柑橘（佛手柑/橙花）、白桃、清甜茶感，整体干净通透',
          '日晒：增加热带水果、芒果、百香果风味，甜感更浓郁，发酵感更明显',
          'CM/厌氧：发酵香气进一步放大，果汁感强烈，风味集中度高',
        ],
      },
      {
        id: '冲煮建议', heading: '冲煮建议',
        body: '瑰夏风味细腻，建议偏低萃取（粉水比 1:16–1:17），水温 92–94°C，研磨中细，重点在于保留花香而非过萃。Comandante C40 推荐刻度 #19–#21，根据豆子新鲜度微调。',
      },
    ],
  },
}

// ── API Functions ─────────────────────────────────────────────────────────
// GET /v1/knowledge/categories
export async function getKbCategories(token?: string | null): Promise<KBCategory[]> {
  if (isApiEnabled) return apiFetch<KBCategory[]>('/knowledge/categories', { token })
  return fallbackKbCategories
}

export async function getKbFilterCategories(token?: string | null): Promise<string[]> {
  if (isApiEnabled) {
    const categories = await getKbCategories(token)
    return ['全部', ...categories.map((category) => category.label)]
  }
  return fallbackKbFilterCategories
}

// GET /v1/knowledge/articles
export async function getArticles(category?: string, q?: string, token?: string | null): Promise<Article[]> {
  if (isApiEnabled) {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    const qs = params.toString()
    return apiFetch<Article[]>(`/knowledge/articles${qs ? `?${qs}` : ''}`, { token })
  }
  return fallbackArticles
}

// GET /v1/knowledge/articles/:slug
export async function getArticle(slug: string, token?: string | null): Promise<Article | null> {
  if (isApiEnabled) {
    try {
      return await apiFetch<Article>(`/knowledge/articles/${slug}`, { token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
  return fallbackArticleDetails[slug]?.article ?? fallbackArticles.find(a => a.slug === slug) ?? null
}

export async function getArticleDetail(slug: string, token?: string | null): Promise<ArticleDetail | null> {
  if (isApiEnabled) {
    try {
      return await apiFetch<ArticleDetail>(`/knowledge/articles/${slug}`, { token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
  const fallback = fallbackArticleDetails[slug]
  if (fallback) {
    return {
      ...fallback.article,
      sections: fallback.body,
    }
  }
  const article = fallbackArticles.find(a => a.slug === slug)
  return article ? { ...article, sections: [] } : null
}

// GET /v1/knowledge/articles/:slug (sections from body field)
export async function getArticleBody(slug: string): Promise<ArticleSection[]> {
  const detail = await getArticleDetail(slug)
  return detail?.sections ?? []
}

// POST /v1/knowledge/ask  (requires auth)
export async function askKnowledge(question: string): Promise<{
  answer: string
  sources: { slug: string; title: string; path: string; excerpt: string }[]
  from_knowledge_base: boolean
  trace_id: string
}> {
  return apiFetch('/knowledge/ask', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}
