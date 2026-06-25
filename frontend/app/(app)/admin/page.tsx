'use client'
// 概览：GET /v1/admin/stats 四组计数 + 最近注册用户（用户列表头页）。
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { getAdminStats, listAdminUsers, type AdminStats, type AdminUserInfo } from '@/lib/api/admin'

const cards: { key: keyof AdminStats; label: string; href: string }[] = [
  { key: 'user_count',              label: '注册用户',  href: '/admin/users' },
  { key: 'active_invite_count',     label: '可用邀请码', href: '/admin/invites' },
  { key: 'pending_proposal_count',  label: '待审提案',  href: '/admin/review?tab=proposals' },
  { key: 'pending_candidate_count', label: '待审候选',  href: '/admin/review?tab=candidates' },
]

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [recent, setRecent] = useState<AdminUserInfo[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getAdminStats(), listAdminUsers(1, 5)])
      .then(([s, users]) => { if (!cancelled) { setStats(s); setRecent(users) } })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : '加载失败') })
    return () => { cancelled = true }
  }, [])

  if (error) return <div className="text-sm text-dc-red">{error}</div>
  if (!stats) return <div className="flex items-center text-dc-text-3 text-sm"><Loader2 size={15} className="animate-spin mr-2" />加载中…</div>

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map(({ key, label, href }) => (
          <Link key={key} href={href} className="dc-card p-5 hover:shadow-md transition-shadow">
            <div className="text-xs text-dc-text-3 mb-1">{label}</div>
            <div className="text-2xl font-bold text-dc-text-1">{stats[key]}</div>
          </Link>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-dc-text-1 mb-3">最近注册</h3>
        <div className="dc-card divide-y divide-dc-border">
          {recent.length === 0 && (
            <div className="px-5 py-6 text-sm text-dc-text-3 text-center">还没有注册用户</div>
          )}
          {recent.map(u => (
            <div key={u.id} className="px-5 py-3 flex items-center gap-4 text-sm">
              <span className="flex-1 truncate text-dc-text-1">{u.email ?? u.id}</span>
              <span className="text-xs text-dc-text-3">{u.plan}</span>
              {u.role === 'admin' && <span className="text-xs text-dc-accent font-medium">admin</span>}
              <span className="text-xs text-dc-text-3 font-mono">{u.invite_code ?? '—'}</span>
              <span className="text-xs text-dc-text-3">{new Date(u.created_at).toLocaleDateString('zh-CN')}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
