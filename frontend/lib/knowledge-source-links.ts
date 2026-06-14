import type { WebVerifySource } from '@/types'

export function normalizeKnowledgeSlug(value: string): string {
  const slug = value
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_.-]+/gu, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
  return slug || 'article'
}

export function slugFromKnowledgePath(path: string): string | null {
  const clean = path.trim().replace(/^knowledge\//, '').replace(/\.md$/i, '')
  if (!clean) return null
  return normalizeKnowledgeSlug(clean.split('/').join('__'))
}

export function sourceHref(source: WebVerifySource): string | null {
  if (source.url?.trim()) return source.url.trim()
  if (source.slug?.trim()) return `/knowledge/${source.slug.trim()}`

  const slug = source.path ? slugFromKnowledgePath(source.path) : null
  return slug ? `/knowledge/${slug}` : null
}

export function isExternalSourceHref(href: string): boolean {
  return href.startsWith('http://') || href.startsWith('https://')
}
