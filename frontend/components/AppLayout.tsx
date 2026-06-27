'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useEffect, useCallback } from 'react'
import {
  MessageCircle, BookOpen, ClipboardList,
  Settings, LayoutGrid, Menu, X, ShieldCheck, Wrench,
} from 'lucide-react'
import InviteGateModal from '@/components/InviteGateModal'
import { ProfileContext } from '@/components/ProfileContext'
import { getUserProfile, getUserQuota } from '@/lib/api/user'
import { ApiError, isApiEnabled } from '@/lib/api/client'
import { getToken, removeToken, setToken } from '@/lib/auth'
import { canBrowseKnowledge, canUseBeanSquare, planLabel as displayPlanLabel, quotaPercent as calcQuotaPercent } from '@/lib/entitlements'
import { supabase } from '@/lib/supabase'
import type { UserProfile, UserQuota } from '@/types'

// getSession 超时兜底用：到点 resolve 一个「未取到会话」结果，与 getSession 竞速。
const sessionTimeout = (ms: number) =>
  new Promise<{ ok: false }>((resolve) => setTimeout(() => resolve({ ok: false as const }), ms))

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

  // 账户信息加载：profile/quota 用 allSettled 解耦——一个失败不连累另一个（用量挂了账户名照常显示）。
  // 抽成可复用函数，供初次加载与「重试」按钮调用。
  const loadAccount = useCallback(async (token: string) => {
    setAccountLoading(true)
    setAccountError('')
    const [profileRes, quotaRes] = await Promise.allSettled([
      getUserProfile(token),
      getUserQuota(token),
    ])
    if (profileRes.status === 'fulfilled') {
      setProfile(profileRes.value)
    } else {
      const error = profileRes.reason
      // token 被后端拒（401）→ 视为已登出，清理并回 landing
      if (error instanceof ApiError && error.status === 401) {
        removeToken()
        supabase.auth.signOut().catch(() => {})
        router.replace('/')
        return
      }
      // 其它（网络 / 超时等暂时性错误）：用户仍登录，只提示、不误登出
      setAccountError(error instanceof Error ? error.message : '账户信息加载失败')
    }
    // 用量失败不阻断账户主体：保持 quota=null（界面显示「暂不可用」）。
    if (quotaRes.status === 'fulfilled') setQuota(quotaRes.value)
    setAccountLoading(false)
  }, [router])

  // Auth guard：以 Supabase 会话为登录态权威。getSession() 会按需用长效 refresh token 自动换新
  // access_token（持久），拿不到会话=未登录/已过期 → 清本地并回 landing 登出，绝不卡在登录后页面。
  // 但 getSession() 自身无超时，移动网抖动时会永久挂起 → 这里加 8s 超时兜底：超时则用本地 token
  // 继续（真过期由后端 401 兜底登出），不再永久卡在「载入中」。dev token（dev: 前缀）走旁路。
  useEffect(() => {
    let cancelled = false
    async function init() {
      setAccountLoading(true)
      setAccountError('')
      let token = getToken()
      const isDevToken = token?.startsWith('dev:') ?? false
      if (!isDevToken) {
        const result = await Promise.race([
          supabase.auth
            .getSession()
            .then(({ data }) => ({ ok: true as const, session: data.session }))
            .catch(() => ({ ok: false as const })),
          sessionTimeout(8000),
        ])
        if (cancelled) return
        if (result.ok) {
          if (!result.session) {
            // getSession 明确返回无会话（未登录或 refresh token 已失效）→ 登出回 landing
            removeToken()
            router.replace('/')
            return
          }
          token = result.session.access_token
          setToken(token) // 写回刷新后的最新 token，后续请求都用它
        } else if (!token) {
          // 超时/失败且本地也没有 token → 当未登录处理
          router.replace('/')
          return
        }
        // 超时但有本地 token：兜底继续用它（过期由后端 401 接住），不卡死。
      }
      if (!token) {
        router.replace('/')
        return
      }
      if (cancelled) return
      await loadAccount(token)
    }
    void init()
    return () => { cancelled = true }
  }, [router, loadAccount])

  // 运行期同步 Supabase 会话 token：刷新后写回 dc_auth_token；登出则清理并回 landing。
  // 不处理 INITIAL_SESSION（冷启动由上面的守卫 getSession 负责），也不在无会话时清掉本地 dev token。
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if ((event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') && session) {
        setToken(session.access_token)
      } else if (event === 'SIGNED_OUT') {
        if (getToken()?.startsWith('dev:')) return
        removeToken()
        router.replace('/')
      }
    })
    return () => data.subscription.unsubscribe()
  }, [router])

  const displayName = profile?.display_name ?? profile?.email ?? '账户'
  const initial = displayName.charAt(0) || '?'
  const planLabel = displayPlanLabel(profile)
  const quotaPercent = calcQuotaPercent(quota)
  const quotaUsageLabel = quota ? `${quotaPercent}%` : '暂不可用'
  const visibleNav: NavItem[] = [
    ...nav,
    ...(canUseBeanSquare(profile) ? [{ label: '豆仓广场', href: '/app/bean-square', icon: LayoutGrid }] : []),
    ...(canBrowseKnowledge(profile) ? [{ label: '知识库', href: '/knowledge', icon: BookOpen }] : []),
    { label: '设置', href: '/app/settings', icon: Settings },
  ]

  // 侧边栏内容（桌面与移动抽屉共用）
  const sidebar = (
    <>
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-dc-border flex-shrink-0">
        <Link href="/app" className="flex items-center gap-2.5">
          <img src="/logo.png" alt="DeepCoffee" className="h-8 w-8 object-contain" />
          <span className="text-lg font-extrabold tracking-tight text-dc-text-1">DeepCoffee</span>
        </Link>
      </div>

      {/* Nav（管理员追加管理后台入口） */}
      <nav className="flex-1 py-4 px-3 flex flex-col gap-0.5 overflow-y-auto">
        {[...visibleNav, ...(profile?.role === 'admin' ? [{ label: '管理后台', href: '/admin', icon: ShieldCheck }] : [])].map(({ label, href, icon: Icon }) => {
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
          <div className="flex justify-between items-center">
            <span className="text-xs text-dc-text-3">本月 AI 用量</span>
            <span className="text-xs font-semibold text-dc-accent">
              {accountLoading ? '载入中' : quotaUsageLabel}
            </span>
          </div>
          {accountError && (
            <div className="mt-1.5 text-xs text-dc-red leading-relaxed">
              {accountError}
              <button
                onClick={() => { const t = getToken(); if (t) void loadAccount(t) }}
                className="ml-1.5 underline font-medium hover:text-dc-text-1"
              >
                重试
              </button>
            </div>
          )}
          {quota && (
            <div className="mt-1.5 h-1.5 bg-dc-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${quotaPercent > 80 ? 'bg-dc-yellow' : 'bg-dc-accent'}`}
                style={{ width: `${quotaPercent}%` }}
              />
            </div>
          )}
          <Link href="/app/settings?tab=plan" className="text-xs text-dc-accent mt-1.5 block hover:underline">
            升级会员 →
          </Link>
        </div>
        <div>
          <Link href="/app/settings" className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-dc-subtle min-w-0">
            <div className="w-7 h-7 rounded-full bg-dc-accent flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {initial}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-dc-text-1 truncate">{displayName}</div>
              <div className="text-xs text-dc-text-3">{planLabel}</div>
            </div>
          </Link>
        </div>
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
          <Link href="/app" className="flex items-center gap-2">
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
