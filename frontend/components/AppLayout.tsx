'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import {
  MessageCircle, BookOpen, ClipboardList,
  Settings, ChevronRight, LayoutGrid, Menu, X, ShieldCheck, Wrench,
} from 'lucide-react'
import InviteGateModal from '@/components/InviteGateModal'
import { ProfileContext } from '@/components/ProfileContext'
import { getUserProfile, getUserQuota } from '@/lib/api/user'
import { ApiError, isApiEnabled } from '@/lib/api/client'
import { getToken, removeToken, setToken } from '@/lib/auth'
import { supabase } from '@/lib/supabase'
import type { UserProfile, UserQuota } from '@/types'

interface NavItem {
  label: string
  href: string
  icon: React.ElementType
}

const nav: NavItem[] = [
  { label: 'Deepcoffee AI', href: '/app/chat',      icon: MessageCircle },
  { label: '我的豆仓',      href: '/app/beans',     icon: LayoutGrid },
  { label: '冲煮记录',      href: '/app/records',   icon: ClipboardList },
  { label: '我的器具',      href: '/app/equipment', icon: Wrench },
  { label: '知识库',        href: '/knowledge',     icon: BookOpen },
  { label: '设置',          href: '/app/settings',  icon: Settings },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [quota, setQuota] = useState<UserQuota | null>(null)
  const [accountLoading, setAccountLoading] = useState(true)
  const [accountError, setAccountError] = useState('')

  // 路由变化时自动关闭移动端抽屉
  useEffect(() => { setOpen(false) }, [path])

  // Auth guard：无 token 跳转登录页
  useEffect(() => {
    const token = getToken()
    if (!token) {
      router.replace('/auth')
      return
    }
    let cancelled = false
    setAccountLoading(true)
    setAccountError('')
    Promise.all([getUserProfile(token), getUserQuota(token)])
      .then(([nextProfile, nextQuota]) => {
        if (cancelled) return
        setProfile(nextProfile)
        setQuota(nextQuota)
      })
      .catch((error) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) {
          removeToken()
          router.replace('/auth')
          return
        }
        setAccountError(error instanceof Error ? error.message : '账户信息加载失败')
      })
      .finally(() => {
        if (!cancelled) setAccountLoading(false)
      })
    return () => { cancelled = true }
  }, [router])

  // 同步 Supabase 会话 token：access_token 默认 1 小时过期，客户端会自动刷新，
  // 这里把刷新后的新 token 写回 dc_auth_token，避免请求带着过期 token 变 401。
  // 仅处理刷新/登入/登出事件，忽略 INITIAL_SESSION，以免清掉本地 dev token。
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if ((event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') && session) {
        setToken(session.access_token)
      } else if (event === 'SIGNED_OUT') {
        removeToken()
      }
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const displayName = profile?.display_name ?? profile?.email ?? '账户'
  const initial = displayName.charAt(0) || '?'
  const planLabel  = profile?.plan === 'pro' ? '会员版' : profile ? '免费版' : '载入中'
  const isUnlimited = quota?.ai_total === null
  const quotaPercent = quota && !isUnlimited && quota.ai_total
    ? Math.min(Math.round((quota.ai_used / quota.ai_total) * 100), 100)
    : 0

  // 侧边栏内容（桌面与移动抽屉共用）
  const sidebar = (
    <>
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-dc-border flex-shrink-0">
        <Link href="/" className="flex items-center gap-2.5">
          <img src="/logo.png" alt="DeepCoffee" className="h-8 w-8 object-contain" />
          <span className="text-lg font-extrabold tracking-tight text-dc-text-1">DeepCoffee</span>
        </Link>
      </div>

      {/* Nav（管理员追加管理后台入口） */}
      <nav className="flex-1 py-4 px-3 flex flex-col gap-0.5 overflow-y-auto">
        {[...nav, ...(profile?.role === 'admin' ? [{ label: '管理后台', href: '/admin', icon: ShieldCheck }] : [])].map(({ label, href, icon: Icon }) => {
          const active = path === href || (href !== '/app' && path.startsWith(href))
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? 'bg-dc-accent-light text-dc-accent'
                  : 'text-dc-text-2 hover:bg-dc-subtle hover:text-dc-text-1'
              }`}
            >
              <Icon size={16} strokeWidth={active ? 2.5 : 1.8} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Quota / User */}
      <div className="p-3 border-t border-dc-border space-y-2 flex-shrink-0">
        <div className="px-3 py-2.5 rounded-lg bg-dc-subtle">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-dc-text-3">本月 AI 用量</span>
            <span className="text-xs font-semibold text-dc-accent">
              {accountLoading
                ? '载入中'
                : quota
                ? `${quota.ai_used} / ${isUnlimited ? '∞' : quota.ai_total}`
                : '暂不可用'}
            </span>
          </div>
          {accountError && (
            <div className="text-xs text-dc-red leading-relaxed">{accountError}</div>
          )}
          {quota && !isUnlimited && (
            <div className="h-1.5 bg-dc-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${quotaPercent > 80 ? 'bg-dc-yellow' : 'bg-dc-accent'}`}
                style={{ width: `${quotaPercent}%` }}
              />
            </div>
          )}
          <Link href="/app/settings" className="text-xs text-dc-accent mt-1.5 block hover:underline">
            升级会员 →
          </Link>
        </div>
        <Link href="/app/settings" className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-dc-subtle">
          <div className="w-7 h-7 rounded-full bg-dc-accent flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {initial}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-dc-text-1 truncate">{displayName}</div>
            <div className="text-xs text-dc-text-3">{planLabel}</div>
          </div>
          <ChevronRight size={14} className="text-dc-text-3" />
        </Link>
      </div>
    </>
  )

  // 后端邀请门禁：账号未绑定邀请码时阻断业务操作，补码成功后重取 profile
  const needsInvite = isApiEnabled && profile != null && profile.invite_bound === false && profile.role !== 'admin'

  return (
    <ProfileContext.Provider value={{ profile, loading: accountLoading }}>
    <div className="flex h-screen bg-dc-bg overflow-hidden">
      {needsInvite && (
        <InviteGateModal onBound={() => {
          const token = getToken()
          if (token) getUserProfile(token).then(setProfile).catch(() => {})
        }} />
      )}

      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-52 flex-shrink-0 flex-col border-r border-dc-border bg-white">
        {sidebar}
      </aside>

      {/* Mobile drawer (slide-in) */}
      <div className={`md:hidden fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`}>
        <div
          className={`absolute inset-0 bg-black/30 transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setOpen(false)}
        />
        <aside
          className={`relative w-64 max-w-[80%] h-full flex flex-col bg-white shadow-xl transition-transform duration-300 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        >
          <button
            onClick={() => setOpen(false)}
            aria-label="关闭菜单"
            className="absolute top-4 right-3 z-10 p-1.5 rounded-lg text-dc-text-3 hover:bg-dc-subtle"
          >
            <X size={18} />
          </button>
          {sidebar}
        </aside>
      </div>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden h-14 flex items-center gap-3 px-4 border-b border-dc-border bg-white flex-shrink-0">
          <button
            onClick={() => setOpen(true)}
            aria-label="打开菜单"
            className="p-1.5 -ml-1.5 text-dc-text-2 hover:text-dc-text-1"
          >
            <Menu size={22} />
          </button>
          <Link href="/" className="flex items-center gap-2">
            <img src="/logo.png" alt="DeepCoffee" className="h-7 w-7 object-contain" />
            <span className="text-base font-extrabold tracking-tight text-dc-text-1">DeepCoffee</span>
          </Link>
        </header>

        <main className="flex-1 overflow-y-auto min-h-0">
          {children}
        </main>
      </div>
    </div>
    </ProfileContext.Provider>
  )
}
