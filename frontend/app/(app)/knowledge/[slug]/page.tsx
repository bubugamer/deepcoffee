import Link from 'next/link'
import type { ReactNode } from 'react'
import { ArrowLeft, MessageSquare } from 'lucide-react'
import { getArticleDetail } from '@/lib/api/knowledge'

const ROOT_KNOWLEDGE_DIRS = new Set([
  'brewing',
  'coffee-sources',
  'competitions',
  'equipment',
  'figures',
  'green-bean-products',
  'green-merchants',
  'guides',
  'origins',
  'processing',
  'roaster-products',
  'roasters',
  'standards',
  'varietals',
])

function normalizeSlug(value: string): string {
  return (
    value
      .normalize('NFKC')
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}_.-]+/gu, '-')
      .replace(/-{2,}/g, '-')
      .replace(/^-+|-+$/g, '') || 'article'
  )
}

function resolveMarkdownHref(href: string, basePath?: string): string {
  const clean = href.trim()
  const lower = clean.toLowerCase()
  if (
    clean.startsWith('#') ||
    lower.startsWith('http://') ||
    lower.startsWith('https://') ||
    lower.startsWith('mailto:') ||
    lower.startsWith('tel:')
  ) {
    return clean
  }

  const [rawPath, rawHash] = clean.split('#', 2)
  if (!rawPath.endsWith('.md')) return clean

  let targetPath = rawPath.replace(/\\/g, '/').replace(/^\/+/, '')
  if (targetPath.startsWith('knowledge/')) targetPath = targetPath.slice('knowledge/'.length)

  const targetParts = targetPath.split('/').filter(Boolean)
  const baseParts = basePath?.replace(/\\/g, '/').split('/').filter(Boolean) ?? []
  const shouldResolveFromBase =
    targetParts.length > 0 && !ROOT_KNOWLEDGE_DIRS.has(targetParts[0])

  const parts = shouldResolveFromBase ? [...baseParts.slice(0, -1), ...targetParts] : targetParts
  const resolved: string[] = []
  for (const part of parts) {
    if (part === '.' || !part) continue
    if (part === '..') {
      resolved.pop()
      continue
    }
    resolved.push(part)
  }

  const withoutSuffix = resolved.map((part, index) =>
    index === resolved.length - 1 ? part.replace(/\.md$/, '') : part
  )
  const slug = withoutSuffix.map(normalizeSlug).join('__')
  const hash = rawHash ? `#${normalizeSlug(rawHash)}` : ''
  return `/knowledge/${slug}${hash}`
}

function renderInline(text: string, basePath?: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*([^*]+)\*\*)|\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))
    if (match[2]) {
      nodes.push(<strong key={nodes.length}>{match[2]}</strong>)
    } else if (match[3] && match[4]) {
      const href = resolveMarkdownHref(match[4], basePath)
      const isExternal = href.startsWith('http://') || href.startsWith('https://')
      nodes.push(
        <a
          key={nodes.length}
          href={href}
          target={isExternal ? '_blank' : undefined}
          rel={isExternal ? 'noreferrer' : undefined}
          className="text-dc-accent hover:underline"
        >
          {match[3]}
        </a>
      )
    }
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function parseTable(lines: string[], start: number, basePath?: string): { node: ReactNode; next: number } | null {
  if (start + 1 >= lines.length) return null
  const header = lines[start].trim()
  const divider = lines[start + 1].trim()
  if (!header.includes('|') || !/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(divider)) return null

  const split = (line: string) =>
    line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())

  const headers = split(header)
  const rows: string[][] = []
  let i = start + 2
  while (i < lines.length && lines[i].trim().includes('|')) {
    rows.push(split(lines[i]))
    i += 1
  }

  return {
    node: (
      <div key={start} className="overflow-x-auto rounded-md border border-dc-border">
        <table className="w-full text-sm">
          <thead className="bg-dc-subtle">
            <tr>
              {headers.map((cell, index) => (
                <th key={index} className="px-3 py-2 text-left font-semibold text-dc-text-1">
                  {renderInline(cell, basePath)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-dc-border">
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {headers.map((_, cellIndex) => (
                  <td key={cellIndex} className="px-3 py-2 align-top text-dc-text-2">
                    {renderInline(row[cellIndex] ?? '', basePath)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
    next: i,
  }
}

// 后端已剥离 frontmatter；此处仅作防御性兜底，避免残留 YAML 头渲染成正文。
function stripFrontmatter(md: string): string {
  if (!md.startsWith('---')) return md
  const close = md.indexOf('\n---', 3)
  if (close === -1) return md
  const after = md.indexOf('\n', close + 1)
  return after === -1 ? '' : md.slice(after + 1)
}

function MarkdownBody({ markdown, basePath }: { markdown: string; basePath?: string }) {
  const lines = stripFrontmatter(markdown).split('\n')
  const nodes: ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const line = raw.trim()
    if (!line) {
      i += 1
      continue
    }

    const h2 = line.match(/^##\s+(.+)$/)
    const h3 = line.match(/^###\s+(.+)$/)
    const h1 = line.match(/^#\s+(.+)$/)
    if (h1) {
      i += 1
      continue
    }
    if (h2) {
      nodes.push(<h2 key={i} className="text-base font-bold text-dc-text-1 mt-8 mb-3">{h2[1]}</h2>)
      i += 1
      continue
    }
    if (h3) {
      nodes.push(<h3 key={i} className="text-sm font-semibold text-dc-text-1 mt-6 mb-2">{h3[1]}</h3>)
      i += 1
      continue
    }

    const table = parseTable(lines, i, basePath)
    if (table) {
      nodes.push(table.node)
      i = table.next
      continue
    }

    if (line.startsWith('- ')) {
      const items: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('- ')) {
        items.push(lines[i].trim().slice(2))
        i += 1
      }
      nodes.push(
        <ul key={i} className="space-y-2">
          {items.map(item => (
            <li key={item} className="flex gap-2 text-dc-text-2">
              <span className="text-dc-accent mt-0.5 flex-shrink-0">·</span>
              <span>{renderInline(item, basePath)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''))
        i += 1
      }
      nodes.push(
        <ol key={i} className="list-decimal space-y-2 pl-5 text-dc-text-2">
          {items.map(item => <li key={item}>{renderInline(item, basePath)}</li>)}
        </ol>
      )
      continue
    }

    if (line.startsWith('>')) {
      nodes.push(
        <blockquote key={i} className="border-l-2 border-dc-accent-hi pl-4 text-dc-text-2">
          {renderInline(line.replace(/^>\s?/, ''), basePath)}
        </blockquote>
      )
      i += 1
      continue
    }

    const paragraph: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith('#') &&
      !lines[i].trim().startsWith('- ') &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !parseTable(lines, i, basePath)
    ) {
      paragraph.push(lines[i].trim())
      i += 1
    }
    nodes.push(<p key={i} className="text-dc-text-2">{renderInline(paragraph.join(' '), basePath)}</p>)
  }

  return <div className="space-y-4 text-sm leading-loose text-dc-text-1">{nodes}</div>
}

export default async function ArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  let error = ''
  const article = await getArticleDetail(slug).catch((err) => {
    error = err instanceof Error ? err.message : '文章加载失败，请稍后重试。'
    return null
  })

  if (error) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/knowledge" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回知识库
        </Link>
        <div className="dc-card p-6">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">文章暂时不可用</div>
          <p className="text-sm text-dc-text-3">{error}</p>
        </div>
      </div>
    )
  }

  if (!article) {
    return (
      <div className="p-4 sm:p-8 max-w-content mx-auto">
        <Link href="/knowledge" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
          <ArrowLeft size={15} />
          返回知识库
        </Link>
        <div className="dc-card p-8 text-center">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">没有找到这篇文章</div>
          <p className="text-sm text-dc-text-3">它可能已被移动，或还没有同步到知识库。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-dc-text-3 mb-6">
        <Link href="/knowledge" className="hover:text-dc-accent flex items-center gap-1">
          <ArrowLeft size={14} /> 知识库
        </Link>
        <span>›</span>
        <span>{article.cat}</span>
        <span>›</span>
        <span className="text-dc-text-2">{article.title}</span>
      </div>

      <div className="grid md:grid-cols-[1fr_220px] gap-8">

        {/* Article body */}
        <article>
          <div className="dc-tag-accent mb-4 w-fit">{article.cat}</div>
          <h1 className="text-2xl font-extrabold text-dc-text-1 mb-2 tracking-tight">{article.title}</h1>
          {article.updated && (
            <div className="text-xs text-dc-text-3 mb-8">最后更新：{article.updated}</div>
          )}

          {article.markdown ? (
            <MarkdownBody markdown={article.markdown} basePath={article.path} />
          ) : article.sections.length === 0 ? (
            <div className="dc-card p-6 text-sm text-dc-text-3">这篇文章还没有正文内容。</div>
          ) : (
            <div className="space-y-8 text-sm leading-loose text-dc-text-1">
              {article.sections.map(section => (
                <section key={section.id} id={section.id}>
                  <h2 className="text-base font-bold text-dc-text-1 mb-3">{section.heading}</h2>
                  {section.body && <p className="text-dc-text-2">{section.body}</p>}
                  {section.items && (
                    <ul className="space-y-2">
                      {section.items.map(item => (
                        <li key={item} className="flex gap-2 text-dc-text-2">
                          <span className="text-dc-accent mt-0.5 flex-shrink-0">·</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>
          )}

          {/* Ask AI CTA */}
          <Link
            href="/app/chat"
            className="mt-10 dc-card p-5 flex items-center gap-4 hover:border-dc-accent-hi transition-colors block"
          >
            <div className="w-10 h-10 rounded-full bg-dc-accent flex-shrink-0 flex items-center justify-center">
              <MessageSquare size={18} className="text-white" strokeWidth={1.8} />
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-dc-text-1 mb-0.5">问 AI 关于这篇内容</div>
              <div className="text-xs text-dc-text-3">直接向 AI 提问，基于知识库内容回答</div>
            </div>
            <span className="text-sm text-dc-accent font-medium flex-shrink-0">去提问 →</span>
          </Link>
        </article>

        {/* Sidebar */}
        <aside className="space-y-5">
          {/* TOC */}
          {article.toc && article.toc.length > 0 && (
            <div className="dc-card p-4 sticky top-6">
              <h3 className="text-xs font-semibold text-dc-text-3 uppercase tracking-wide mb-3">目录</h3>
              <nav className="space-y-1">
                {article.toc.map(item => (
                  <a
                    key={item.id}
                    href={`#${item.id}`}
                    className={`block text-sm text-dc-text-2 py-1 rounded hover:bg-dc-subtle hover:text-dc-accent transition-colors ${
                      item.level === 3 ? 'px-4 text-xs' : 'px-2'
                    }`}
                  >
                    {item.title}
                  </a>
                ))}
              </nav>
            </div>
          )}

          {/* Related */}
          {article.related && article.related.length > 0 && (
            <div className="dc-card p-4">
              <h3 className="text-xs font-semibold text-dc-text-3 uppercase tracking-wide mb-3">相关文章</h3>
              <div className="space-y-1">
                {article.related.map(r => (
                  <Link
                    key={r.slug}
                    href={`/knowledge/${r.slug}`}
                    className="block text-sm text-dc-text-2 py-1.5 px-2 rounded hover:bg-dc-subtle hover:text-dc-accent transition-colors"
                  >
                    {r.title}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
