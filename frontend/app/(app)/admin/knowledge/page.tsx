'use client'
// 知识库运维：POST /v1/admin/knowledge/reload，并展示返回的统计。
import { useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import { reloadKnowledge, type KnowledgeReloadResult } from '@/lib/api/admin'

export default function AdminKnowledgePage() {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<KnowledgeReloadResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleReload() {
    setRunning(true)
    setError(null)
    try {
      setResult(await reloadKnowledge())
    } catch (err) {
      setError(err instanceof Error ? err.message : '重载失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="max-w-xl">
      <div className="dc-card p-6 space-y-4">
        <div>
          <h3 className="text-base font-bold text-dc-text-1 mb-1">知识库重载</h3>
          <p className="text-sm text-dc-text-3 leading-relaxed">
            把 knowledge/ 目录下的 Markdown 重新扫描入库（Markdown 是公共知识内容的唯一事实源）。
          </p>
        </div>
        <button
          onClick={handleReload}
          disabled={running}
          className="btn-primary px-5 py-2.5 text-sm disabled:opacity-60 flex items-center gap-2"
        >
          {running ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          重新加载
        </button>
        {error && <p className="text-sm text-dc-red">{error}</p>}
        {result && (
          <div className="bg-dc-subtle rounded-lg p-4 text-sm text-dc-text-2 space-y-1">
            <div>公开文章 {result.public_article_count} 篇（扫描 {result.scanned_markdown_count} 个 Markdown，可检索 {result.indexable_article_count} 篇）</div>
            <div>分类 {result.category_count} 个 · 公共实体 {result.entity_count} 个</div>
            <div className="text-xs text-dc-text-3">reloaded_at {result.reloaded_at}</div>
          </div>
        )}
      </div>
    </div>
  )
}
