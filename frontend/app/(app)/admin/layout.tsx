'use client'
// 管理后台框架：AdminGuard（role !== 'admin' 一律 403）+ 顶部子导航。
// 外层 AppLayout 已处理登录态并取过 /me，这里直接消费 ProfileContext，
// 不再发起第二次请求——后端 require_admin 才是真正的强制层，这里只是体验层。
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Loader2, ShieldOff } from 'lucide-react'
import { useProfile } from '@/components/ProfileContext'

const adminNav = [
  { label: '概览',   href: '/admin' },
  { label: '邀请码', href: '/admin/invites' },
  { label: '用户',   href: '/admin/users' },
  { label: '审核',   href: '/admin/review' },
  { label: '知识库', href: '/admin/knowledge' },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname()
  const { profile, loading } = useProfile()

  if (loading && profile == null) {
    return (
      <div className="flex items-center justify-center h-64 text-dc-text-3">
        <Loader2 size={18} className="animate-spin mr-2" /> 载入中…
      </div>
    )
  }

  if (profile?.role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center h-72 text-center px-4">
        <ShieldOff size={36} className="text-dc-text-3 mb-4" />
        <h2 className="text-lg font-bold text-dc-text-1 mb-2">无权访问</h2>
        <p className="text-sm text-dc-text-3 mb-5">该区域仅限管理员使用。</p>
        <Link href="/app" className="btn-primary px-5 py-2.5 text-sm">返回应用</Link>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-8 py-6">
      <div className="flex items-center gap-1 border-b border-dc-border mb-6 overflow-x-auto">
        {adminNav.map(({ label, href }) => {
          const active = href === '/admin' ? path === '/admin' : path.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
                active
                  ? 'border-dc-accent text-dc-accent'
                  : 'border-transparent text-dc-text-3 hover:text-dc-text-1'
              }`}
            >
              {label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}
