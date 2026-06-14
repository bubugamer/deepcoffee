'use client'
import Link from 'next/link'
import { useState, useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Coffee, CheckCircle2, XCircle, Loader2, MailCheck, AlertTriangle } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import { setToken } from '@/lib/auth'
import { redeemInviteCode, validateInviteCode } from '@/lib/api/user'
import { ApiError, isApiEnabled } from '@/lib/api/client'

// error：validate 请求本身失败（网络/服务异常），可点击重试——不能静默回 idle，
// 否则用户会卡在「按钮永远置灰」且不知道原因。
type InviteState = 'idle' | 'checking' | 'valid' | 'invalid' | 'error'

// 邮箱确认流程下注册时拿不到 token，先暂存邀请码，待首次登录后补 redeem
const PENDING_INVITE_KEY = 'dc_pending_invite'

// 重发确认邮件的前端冷却（秒）。Supabase 自身也有频率限制，这里先挡一道。
const RESEND_COOLDOWN_S = 60

// 注册成功 ≠ 邀请码已消费：后端看不到 Supabase 注册事件，
// 必须在拿到 token 后主动调 redeem，否则邀请码永远不会被标记为已用。
// redeem 失败（如该码刚被他人用掉）时账号已在 Supabase 建好，放行进应用，仅在控制台告警。
async function consumeInvite(code: string, token: string) {
  if (!isApiEnabled || !code) return
  try {
    await redeemInviteCode(code, token)
  } catch (err) {
    console.warn('邀请码消费失败（账号已创建，放行）：', err)
  }
}

async function consumePendingInvite(token: string) {
  if (!isApiEnabled) return
  const code = localStorage.getItem(PENDING_INVITE_KEY)
  if (!code) return
  try {
    await redeemInviteCode(code, token)
    localStorage.removeItem(PENDING_INVITE_KEY)
  } catch (err) {
    // 码已失效（400）就不再重试；网络类错误保留，下次登录再试
    if (err instanceof ApiError && err.status === 400) localStorage.removeItem(PENDING_INVITE_KEY)
  }
}

// gee****@gmail.com 式遮蔽，验证引导屏展示用
function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return email
  const visible = local.slice(0, Math.min(3, local.length))
  return `${visible}****@${domain}`
}

function AuthInner() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [tab, setTab] = useState<'login' | 'register'>(
    searchParams.get('tab') === 'register' ? 'register' : 'login'
  )

  // Form fields
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')

  // UI state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [inviteState, setInviteState] = useState<InviteState>('idle')
  const [revalidateTick, setRevalidateTick] = useState(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 校验请求序号：快速连续输入时丢弃过期响应，避免旧结果覆盖新状态
  const validateSeqRef = useRef(0)

  // 邮箱验证引导屏：非 null 时整卡替换为「查收邮件」界面
  const [pendingVerifyEmail, setPendingVerifyEmail] = useState<string | null>(null)
  const [resendCooldown, setResendCooldown] = useState(0)
  const [resendMsg, setResendMsg] = useState<string | null>(null)

  // Invite code validation (debounced)
  useEffect(() => {
    if (!inviteCode.trim() || !isApiEnabled) {
      setInviteState('idle')
      return
    }
    setInviteState('checking')
    const seq = ++validateSeqRef.current
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await validateInviteCode(inviteCode.trim().toUpperCase())
        if (seq === validateSeqRef.current) setInviteState(res.valid ? 'valid' : 'invalid')
      } catch {
        if (seq === validateSeqRef.current) setInviteState('error')
      }
    }, 600)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [inviteCode, revalidateTick])

  // 重发冷却倒计时
  useEffect(() => {
    if (resendCooldown <= 0) return
    const t = setTimeout(() => setResendCooldown(s => s - 1), 1000)
    return () => clearTimeout(t)
  }, [resendCooldown])

  function clearForm() {
    setError(null)
    setSuccessMsg(null)
  }

  // ── Login ──────────────────────────────────────────────────────────────────
  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!email || !password) { setError('请填写邮箱和密码'); return }
    setLoading(true)
    try {
      const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password })
      if (authError) {
        setError(authError.message === 'Invalid login credentials'
          ? '邮箱或密码错误'
          : authError.message)
        return
      }
      setToken(data.session.access_token)
      await consumePendingInvite(data.session.access_token)
      router.push('/app')
    } finally {
      setLoading(false)
    }
  }

  // ── Register ───────────────────────────────────────────────────────────────
  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!email || !password) { setError('请填写邮箱和密码'); return }
    if (password !== confirmPassword) { setError('两次密码不一致'); return }
    if (password.length < 8) { setError('密码至少 8 位'); return }
    // 防御性兜底：正常情况下按钮在非 valid 状态下不可点，到不了这里
    if (isApiEnabled && inviteState !== 'valid') { setError('请输入有效的邀请码'); return }
    setLoading(true)
    try {
      const { data, error: authError } = await supabase.auth.signUp({ email, password })
      if (authError) {
        setError(authError.message)
        return
      }
      const code = inviteCode.trim().toUpperCase()
      if (data.session) {
        // Email confirmation disabled — session returned immediately
        setToken(data.session.access_token)
        await consumeInvite(code, data.session.access_token)
        router.push('/app')
      } else {
        // Email confirmation required：此时没有 token，暂存邀请码，首次登录后补 redeem。
        // 进入「查收邮件」引导屏（不再只是切回登录 tab + 一行提示）。
        if (isApiEnabled && code) localStorage.setItem(PENDING_INVITE_KEY, code)
        setPendingVerifyEmail(email)
        setResendCooldown(RESEND_COOLDOWN_S)
        setResendMsg(null)
      }
    } finally {
      setLoading(false)
    }
  }

  // 重发确认邮件（对同一未确认账号重发，不产生新账号）
  async function handleResend() {
    if (!pendingVerifyEmail || resendCooldown > 0) return
    setResendMsg(null)
    const { error: resendError } = await supabase.auth.resend({ type: 'signup', email: pendingVerifyEmail })
    if (resendError) {
      const rate = resendError.status === 429 || /rate|seconds/i.test(resendError.message)
      setResendMsg(rate ? '发送过于频繁，请稍后再试' : `发送失败：${resendError.message}`)
      if (rate) setResendCooldown(RESEND_COOLDOWN_S)
      return
    }
    setResendMsg('邮件已重新发送')
    setResendCooldown(RESEND_COOLDOWN_S)
  }

  function backToLogin() {
    setPendingVerifyEmail(null)
    setTab('login')
    clearForm()
    setSuccessMsg('验证完成后，用注册邮箱直接登录即可。')
  }

  // 仅本地开发且 API 也指向本机时，才允许 dev token 跳过 Supabase 流程。
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? ''
  const isLocalApi = !apiBase || /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?(?:\/|$)/.test(apiBase)
  const isDev = process.env.NODE_ENV === 'development' && isLocalApi
  function handleDevLogin() {
    setToken('dev:u1:dev@deepcoffee.local')
    router.push('/app')
  }

  // 注册按钮置灰逻辑：邀请码非 valid 一律不可点，并显示原因
  const inviteGateBlocked = isApiEnabled && inviteState !== 'valid'
  const inviteGateReason: string | null = !isApiEnabled ? null : (
    inviteState === 'idle' ? '请输入邀请码' :
    inviteState === 'checking' ? '正在校验邀请码…' :
    inviteState === 'invalid' ? '邀请码无效' :
    inviteState === 'error' ? '邀请码校验失败，请重试' : null
  )

  return (
    <div className="min-h-screen bg-dc-bg flex flex-col items-center justify-center px-4">

      {/* Logo */}
      <Link href="/" className="mb-8 text-xl font-extrabold tracking-tight">
        <span className="text-dc-accent">Deep</span>
        <span className="text-dc-text-1">Coffee</span>
      </Link>

      {/* Card */}
      <div className="dc-card w-full max-w-md p-8">

        {/* ── 邮箱验证引导屏（注册成功且需要确认时整卡替换）── */}
        {pendingVerifyEmail ? (
          <div className="flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-full bg-dc-subtle flex items-center justify-center mb-5">
              <MailCheck size={26} className="text-dc-accent" />
            </div>
            <h2 className="text-lg font-bold text-dc-text-1 mb-3">查收你的邮箱</h2>
            <p className="text-sm text-dc-text-2 leading-relaxed mb-1">
              确认邮件已发送至
            </p>
            <p className="text-sm font-medium text-dc-text-1 mb-4">{maskEmail(pendingVerifyEmail)}</p>
            <p className="text-xs text-dc-text-3 leading-relaxed mb-6">
              点击邮件中的链接完成验证，然后回来登录即可。
            </p>

            <button
              onClick={handleResend}
              disabled={resendCooldown > 0}
              className="btn-primary w-full py-3 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {resendCooldown > 0 ? `重新发送邮件（${resendCooldown}s）` : '重新发送邮件'}
            </button>
            {resendMsg && (
              <p className={`text-xs mt-2 ${resendMsg.startsWith('邮件已') ? 'text-dc-green' : 'text-dc-red'}`}>
                {resendMsg}
              </p>
            )}

            <p className="text-xs text-dc-text-3 mt-5">
              没收到？请检查垃圾邮件 / 广告邮件文件夹
            </p>

            <div className="w-full border-t border-dc-border mt-6 pt-5">
              <button
                onClick={backToLogin}
                className="text-sm text-dc-accent hover:underline"
              >
                已完成验证？去登录
              </button>
            </div>
          </div>
        ) : (
        <>

        {/* Tabs */}
        <div className="flex gap-1 bg-dc-subtle rounded-lg p-1 mb-8">
          {(['login', 'register'] as const).map(t => (
            <button
              key={t}
              onClick={() => { setTab(t); clearForm() }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                tab === t
                  ? 'bg-white text-dc-text-1 shadow-sm'
                  : 'text-dc-text-3 hover:text-dc-text-2'
              }`}
            >
              {t === 'login' ? '登录' : '注册'}
            </button>
          ))}
        </div>

        {/* Global error / success */}
        {error && (
          <div className="mb-4 text-sm text-dc-red bg-red-50 border border-red-100 rounded-lg px-4 py-3">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mb-4 text-sm text-dc-green bg-green-50 border border-green-100 rounded-lg px-4 py-3">
            {successMsg}
          </div>
        )}

        {/* ── Login Form ── */}
        {tab === 'login' && (
          <form className="space-y-4" onSubmit={handleLogin}>
            <div>
              <label className="text-xs text-dc-text-3 mb-1.5 block">邮箱</label>
              <input
                className="dc-input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="text-xs text-dc-text-3">密码</label>
                <span className="text-xs text-dc-accent cursor-pointer hover:underline">忘记密码？</span>
              </div>
              <input
                className="dc-input"
                type="password"
                placeholder="输入密码"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 text-sm mt-2 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              登录
            </button>
          </form>
        )}

        {/* ── Register Form ── */}
        {tab === 'register' && (
          <form className="space-y-4" onSubmit={handleRegister}>
            <div>
              <label className="text-xs text-dc-text-3 mb-1.5 block">邮箱</label>
              <input
                className="dc-input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div>
              <label className="text-xs text-dc-text-3 mb-1.5 block">密码</label>
              <input
                className="dc-input"
                type="password"
                placeholder="至少 8 位"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div>
              <label className="text-xs text-dc-text-3 mb-1.5 block">确认密码</label>
              <input
                className="dc-input"
                type="password"
                placeholder="再输一遍"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div>
              <label className="text-xs text-dc-text-3 mb-1.5 block">
                邀请码 <span className="text-dc-red text-xs">*</span>
              </label>
              <div className="relative">
                <input
                  className={`dc-input pr-9 ${
                    inviteState === 'valid'
                      ? 'border-dc-green ring-1 ring-dc-green/30'
                      : inviteState === 'invalid' || inviteState === 'error'
                      ? 'border-dc-red ring-1 ring-dc-red/20'
                      : ''
                  }`}
                  type="text"
                  placeholder="输入邀请码"
                  value={inviteCode}
                  onChange={e => setInviteCode(e.target.value)}
                  autoCapitalize="characters"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  {inviteState === 'checking' && <Loader2 size={14} className="text-dc-text-3 animate-spin" />}
                  {inviteState === 'valid'    && <CheckCircle2 size={14} className="text-dc-green" />}
                  {inviteState === 'invalid'  && <XCircle size={14} className="text-dc-red" />}
                  {inviteState === 'error'    && <AlertTriangle size={14} className="text-dc-red" />}
                </div>
              </div>
              {inviteState === 'invalid' && (
                <p className="text-xs text-dc-red mt-1">邀请码无效，请确认后重试</p>
              )}
              {inviteState === 'error' && (
                <button
                  type="button"
                  onClick={() => setRevalidateTick(t => t + 1)}
                  className="text-xs text-dc-red mt-1 underline underline-offset-2"
                >
                  校验失败，点击重试
                </button>
              )}
              {inviteState === 'valid' && (
                <p className="text-xs text-dc-green mt-1">邀请码有效</p>
              )}
            </div>
            <button
              type="submit"
              disabled={loading || inviteGateBlocked}
              className="btn-primary w-full py-3 text-sm mt-2 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {(loading || inviteState === 'checking') && <Loader2 size={14} className="animate-spin" />}
              创建账户
            </button>
            {inviteGateBlocked && inviteGateReason && (
              <p className="text-center text-xs text-dc-text-3">{inviteGateReason}</p>
            )}
            <p className="text-center text-xs text-dc-text-3 leading-relaxed">
              注册即表示你同意我们的
              <span className="text-dc-accent cursor-pointer hover:underline mx-1">隐私协议</span>
              和
              <span className="text-dc-accent cursor-pointer hover:underline mx-1">服务条款</span>
            </p>
          </form>
        )}
        </>
        )}
      </div>

      {isDev && !pendingVerifyEmail && (
        <button
          onClick={handleDevLogin}
          className="mt-5 text-xs text-dc-text-3 hover:text-dc-accent border border-dashed border-dc-border rounded-lg px-3 py-2 transition-colors"
        >
          开发者快速登录（dev token）
        </button>
      )}

      <div className="mt-6 flex items-center gap-1.5 text-xs text-dc-text-3">
        <Coffee size={12} />
        Your Coffee Journey Begins
      </div>
    </div>
  )
}

export default function AuthPage() {
  return (
    <Suspense fallback={null}>
      <AuthInner />
    </Suspense>
  )
}
