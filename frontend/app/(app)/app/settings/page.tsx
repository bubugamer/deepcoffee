'use client'
import { FormEvent, Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Check, KeyRound, Loader2, LogOut, X } from 'lucide-react'
import { getBillingPlans, getUserProfile, getUserQuota, maxPlanFeatures, proPlanFeatures, updateUserProfile } from '@/lib/api/user'
import { getToken, removeToken, setToken } from '@/lib/auth'
import { planLabel as displayPlanLabel, quotaPercent as calcQuotaPercent } from '@/lib/entitlements'
import { supabase } from '@/lib/supabase'
import type { BillingPlan, UserProfile, UserQuota } from '@/types'

type Tab = 'profile' | 'plan' | 'prefs'
type SaveState = 'idle' | 'saving' | 'saved' | 'error'
type PasswordState = 'idle' | 'saving' | 'saved' | 'error'

const TABS: Tab[] = ['profile', 'plan', 'prefs']
const planCardFeatures = {
  basic: ['基础 AI 用量', '可使用 AI 知识库问答', '可打开 AI 引用文章'],
  pro: proPlanFeatures,
  max: maxPlanFeatures,
}

function SettingsContent() {
  // 支持 ?tab=plan 直达「配额与会员」（侧边栏「升级会员」入口用）
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = searchParams.get('tab') as Tab | null
  const [tab, setTab] = useState<Tab>(initialTab && TABS.includes(initialTab) ? initialTab : 'profile')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [quota, setQuota] = useState<UserQuota | null>(null)
  const [plans, setPlans] = useState<BillingPlan[]>([])
  const [displayName, setDisplayName] = useState('')
  const [timezone, setTimezone] = useState('Asia/Shanghai')
  const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>('metric')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const [passwordState, setPasswordState] = useState<PasswordState>('idle')
  const [passwordMessage, setPasswordMessage] = useState('')

  useEffect(() => {
    const nextTab = searchParams.get('tab') as Tab | null
    if (nextTab && TABS.includes(nextTab)) setTab(nextTab)
  }, [searchParams])

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      setLoadError('请先登录后再查看设置。')
      return
    }

    let cancelled = false
    setLoading(true)
    setLoadError('')
    // profile/quota 解耦：用 allSettled，用量失败不连累设置主体（个人资料照常加载）。
    Promise.allSettled([getUserProfile(token), getUserQuota(token)])
      .then(([profileRes, quotaRes]) => {
        if (cancelled) return
        if (profileRes.status === 'fulfilled') {
          const nextProfile = profileRes.value
          setProfile(nextProfile)
          setDisplayName(nextProfile.display_name ?? '')
          setTimezone(nextProfile.timezone || 'Asia/Shanghai')
          setUnitSystem(nextProfile.unit_system === 'imperial' ? 'imperial' : 'metric')
        } else {
          const error = profileRes.reason
          setLoadError(error instanceof Error ? error.message : '设置加载失败，请稍后重试。')
        }
        // 用量失败不阻断：保持 quota=null
        if (quotaRes.status === 'fulfilled') setQuota(quotaRes.value)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    // 套餐价格/权益读接口，不写死；失败时静默回退到本地兜底文案
    getBillingPlans()
      .then((plans) => {
        if (!cancelled) setPlans(plans)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  async function saveProfile(event?: FormEvent) {
    event?.preventDefault()
    const token = getToken()
    if (!token) {
      setSaveState('error')
      setSaveMessage('请先登录后再保存。')
      return
    }
    setSaveState('saving')
    setSaveMessage('')
    try {
      const nextProfile = await updateUserProfile({
        display_name: displayName.trim() || undefined,
        timezone,
        unit_system: unitSystem,
      }, token)
      setProfile(nextProfile)
      setDisplayName(nextProfile.display_name ?? '')
      setTimezone(nextProfile.timezone || 'Asia/Shanghai')
      setUnitSystem(nextProfile.unit_system === 'imperial' ? 'imperial' : 'metric')
      setSaveState('saved')
      setSaveMessage('已保存')
    } catch (error) {
      setSaveState('error')
      setSaveMessage(error instanceof Error ? error.message : '保存失败，请稍后重试。')
    }
  }

  async function handleLogout() {
    try { await supabase.auth.signOut() } catch { /* 本地清理仍继续执行 */ }
    removeToken()
    router.replace('/')
  }

  function openPasswordDialog() {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmNewPassword('')
    setPasswordState('idle')
    setPasswordMessage('')
    setPasswordOpen(true)
  }

  function closePasswordDialog() {
    if (passwordState === 'saving') return
    setPasswordOpen(false)
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    if (!profile?.email) {
      setPasswordState('error')
      setPasswordMessage('当前账号缺少邮箱，无法修改密码。')
      return
    }
    if (!currentPassword) {
      setPasswordState('error')
      setPasswordMessage('请输入当前密码。')
      return
    }
    if (newPassword.length < 8) {
      setPasswordState('error')
      setPasswordMessage('新密码至少 8 位。')
      return
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordState('error')
      setPasswordMessage('两次输入的新密码不一致。')
      return
    }

    setPasswordState('saving')
    setPasswordMessage('')
    try {
      const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
        email: profile.email,
        password: currentPassword,
      })
      if (signInError) {
        setPasswordState('error')
        setPasswordMessage(signInError.message === 'Invalid login credentials' ? '当前密码不正确。' : signInError.message)
        return
      }
      if (signInData.session?.access_token) setToken(signInData.session.access_token)

      const { error: updateError } = await supabase.auth.updateUser({ password: newPassword })
      if (updateError) {
        setPasswordState('error')
        setPasswordMessage(updateError.message || '密码修改失败，请稍后重试。')
        return
      }
      const { data: sessionData } = await supabase.auth.getSession()
      if (sessionData.session?.access_token) setToken(sessionData.session.access_token)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmNewPassword('')
      setPasswordState('saved')
      setPasswordMessage('密码已修改。')
    } catch (error) {
      setPasswordState('error')
      setPasswordMessage(error instanceof Error ? error.message : '密码修改失败，请稍后重试。')
    }
  }

  const initial = (displayName || profile?.email || '?').charAt(0)
  const planLabel = displayPlanLabel(profile)
  const joinedAt = profile?.created_at ? profile.created_at.slice(0, 7) : '--'
  const quotaPercent = calcQuotaPercent(quota)
  const resetDate = quota?.reset_at
    ? new Date(quota.reset_at).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
    : ''

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <h1 className="text-xl font-bold text-dc-text-1 mb-6">设置</h1>

      {/* Tabs */}
      <div className="flex gap-1 bg-dc-subtle rounded-lg p-1 mb-8 w-full sm:w-fit overflow-x-auto">
        {([['profile', '个人信息'], ['plan', '配额与会员'], ['prefs', '偏好设置']] as [Tab, string][]).map(([t, l]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === t ? 'bg-white text-dc-text-1 shadow-sm' : 'text-dc-text-3 hover:text-dc-text-2'
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {loading && (
        <div className="dc-card p-6 max-w-lg text-sm text-dc-text-3">正在加载设置…</div>
      )}

      {!loading && loadError && (
        <div className="dc-card p-6 max-w-lg">
          <div className="text-sm font-semibold text-dc-text-1 mb-1">设置暂时不可用</div>
          <p className="text-sm text-dc-text-3">{loadError}</p>
        </div>
      )}

      {!loading && !loadError && profile && (
        <>
          {/* Profile */}
          {tab === 'profile' && (
            <>
              <form onSubmit={saveProfile} className="dc-card p-6 space-y-5 max-w-lg">
                <div className="flex items-center gap-4 pb-5 border-b border-dc-border">
                  <div className="w-14 h-14 rounded-full bg-dc-accent flex items-center justify-center text-white text-xl font-bold">{initial}</div>
                  <div className="min-w-0">
                    <div className="font-semibold text-dc-text-1">{displayName || profile.email}</div>
                    {profile.email && (
                      <div className="text-sm text-dc-text-2 truncate">{profile.email}</div>
                    )}
                    <div className="text-sm text-dc-text-3">{planLabel} · 加入于 {joinedAt}</div>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-dc-text-3 mb-1.5 block">昵称</label>
                  <input
                    className="dc-input"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="请输入昵称"
                  />
                  <div className="flex items-center justify-end gap-3 pt-3">
                    {saveMessage && (
                      <span className={`text-xs ${saveState === 'error' ? 'text-dc-red' : 'text-dc-green'}`}>
                        {saveMessage}
                      </span>
                    )}
                    <button className="btn-primary w-24 text-sm py-2 whitespace-nowrap" disabled={saveState === 'saving'}>
                      {saveState === 'saving' ? '保存中…' : '保存修改'}
                    </button>
                  </div>
                </div>
                <div className="pt-5 border-t border-dc-border flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium text-dc-text-1">
                      <KeyRound size={15} className="text-dc-text-3" />
                      修改登录密码
                    </div>
                    <p className="text-xs text-dc-text-3 mt-1">用于保护当前账号的登录安全。</p>
                  </div>
                  <button
                    type="button"
                    onClick={openPasswordDialog}
                    className="btn-secondary w-24 text-sm py-2 whitespace-nowrap"
                  >
                    修改密码
                  </button>
                </div>
                <div className="pt-5 border-t border-dc-border flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium text-dc-text-1">
                      <LogOut size={15} className="text-dc-text-3" />
                      退出当前账号
                    </div>
                    <p className="text-xs text-dc-text-3 mt-1">退出后需要重新登录才能继续使用。</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="btn-secondary w-24 text-sm py-2 whitespace-nowrap text-dc-red hover:border-dc-red/40 hover:bg-red-50"
                  >
                    退出登录
                  </button>
                </div>
              </form>

              {passwordOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4" onClick={closePasswordDialog}>
                  <div className="dc-card w-full max-w-md p-6" onClick={(event) => event.stopPropagation()}>
                    <div className="flex items-start justify-between gap-4 mb-5">
                      <div>
                        <h2 className="text-base font-bold text-dc-text-1">修改密码</h2>
                        <p className="text-xs text-dc-text-3 mt-1">请输入当前密码，并设置新的登录密码。</p>
                      </div>
                      <button
                        type="button"
                        onClick={closePasswordDialog}
                        className="p-1.5 rounded-lg text-dc-text-3 hover:bg-dc-subtle hover:text-dc-text-1"
                        aria-label="关闭"
                      >
                        <X size={18} />
                      </button>
                    </div>
                    <form onSubmit={changePassword} className="space-y-4">
                      <input className="hidden" type="email" value={profile.email ?? ''} readOnly autoComplete="username" />
                      <div>
                        <label className="text-xs text-dc-text-3 mb-1.5 block">当前密码</label>
                        <input
                          className="dc-input"
                          type="password"
                          value={currentPassword}
                          onChange={(event) => setCurrentPassword(event.target.value)}
                          autoComplete="current-password"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-dc-text-3 mb-1.5 block">新密码</label>
                        <input
                          className="dc-input"
                          type="password"
                          value={newPassword}
                          onChange={(event) => setNewPassword(event.target.value)}
                          autoComplete="new-password"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-dc-text-3 mb-1.5 block">确认新密码</label>
                        <input
                          className="dc-input"
                          type="password"
                          value={confirmNewPassword}
                          onChange={(event) => setConfirmNewPassword(event.target.value)}
                          autoComplete="new-password"
                        />
                      </div>
                      {passwordMessage && (
                        <p className={`text-xs ${passwordState === 'saved' ? 'text-dc-green' : 'text-dc-red'}`}>
                          {passwordMessage}
                        </p>
                      )}
                      <div className="flex items-center justify-end gap-3 pt-1">
                        <button type="button" onClick={closePasswordDialog} className="btn-secondary text-sm px-4 py-2" disabled={passwordState === 'saving'}>
                          取消
                        </button>
                        <button
                          className="btn-primary text-sm px-5 py-2 disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
                          disabled={passwordState === 'saving'}
                        >
                          {passwordState === 'saving' && <Loader2 size={14} className="animate-spin" />}
                          确认修改
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Plan & Quota */}
          {tab === 'plan' && (
            <div className="space-y-5 max-w-xl">
              {/* Quota card */}
              <div className="dc-card p-6">
                <h2 className="section-title mb-4">本月用量</h2>
                {quota ? (
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-dc-text-2">AI 问答</span>
                        <span className="font-semibold text-dc-text-1">
                          已用 {quotaPercent}%
                        </span>
                      </div>
                      <div className="h-2 bg-dc-subtle rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${quotaPercent > 80 ? 'bg-dc-yellow' : 'bg-dc-accent'}`}
                          style={{ width: `${Math.min(quotaPercent, 100)}%` }}
                        />
                      </div>
                    </div>
                    <p className="text-xs text-dc-text-3">
                      记录冲煮、豆卡识别和知识库问答都会计入本月 AI 用量。
                    </p>
                    {resetDate && (
                      <p className="text-xs text-dc-text-3">配额于 {resetDate} 重置</p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-dc-text-3">配额信息暂时不可用。</p>
                )}
              </div>

              <div className="grid gap-4">
                {[
                  { id: 'basic', title: 'Basic', fallbackPrice: 0, features: planCardFeatures.basic },
                  { id: 'pro', title: 'Pro', fallbackPrice: 59, features: planCardFeatures.pro },
                  { id: 'max', title: 'Max', fallbackPrice: 99, features: planCardFeatures.max },
                ].map((plan) => {
                  const apiPlan = plans.find((item) => item.id === plan.id)
                  const active = profile.plan === plan.id
                  return (
                    <div key={plan.id} className={`dc-card p-6 ${active ? 'border-dc-accent ring-1 ring-dc-accent/20' : ''}`}>
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="section-title">{plan.title}</h2>
                        {active && <span className="dc-tag-accent">当前套餐</span>}
                      </div>
                      <div className="text-3xl font-extrabold text-dc-text-1 mb-1">
                        ¥{apiPlan?.price ?? plan.fallbackPrice} <span className="text-sm font-normal text-dc-text-3">/ 月</span>
                      </div>
                      <p className="text-xs text-dc-text-3 mb-5">{plan.id === 'basic' ? '免费使用' : '支付暂未开放，可联系管理员开通'}</p>
                      <ul className="space-y-2.5 mb-5">
                        {plan.features.map(f => (
                          <li key={f} className="flex items-center gap-2 text-sm text-dc-text-2">
                            <Check size={13} className="text-dc-accent flex-shrink-0" />
                            {f}
                          </li>
                        ))}
                      </ul>
                      {plan.id !== 'basic' && <button className="btn-primary w-full py-3 text-sm opacity-70 cursor-not-allowed" disabled>支付暂未开放</button>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Preferences */}
          {tab === 'prefs' && (
            <form onSubmit={saveProfile} className="dc-card p-6 space-y-5 max-w-lg">
              <div>
                <label className="text-xs text-dc-text-3 mb-1.5 block">重量单位</label>
                <div className="flex gap-2">
                  {(['metric', 'imperial'] as const).map((u) => (
                    <button
                      type="button"
                      key={u}
                      onClick={() => setUnitSystem(u)}
                      className={`flex-1 py-2 text-sm rounded-lg border transition-colors ${
                        unitSystem === u
                          ? 'border-dc-accent bg-dc-accent-light text-dc-accent font-medium'
                          : 'border-dc-border text-dc-text-2 bg-white'
                      }`}
                    >
                      {u === 'metric' ? '克（g）' : '盎司（oz）'}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-dc-text-3 mb-1.5 block">时区</label>
                <select className="dc-input" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                  <option value="Asia/Shanghai">Asia/Shanghai（UTC+8）</option>
                  <option value="Asia/Tokyo">Asia/Tokyo（UTC+9）</option>
                  <option value="America/Los_Angeles">America/Los_Angeles（UTC-7）</option>
                </select>
              </div>
              <div className="flex items-center gap-3">
                <button className="btn-primary text-sm px-5 py-2" disabled={saveState === 'saving'}>
                  {saveState === 'saving' ? '保存中…' : '保存偏好'}
                </button>
                {saveMessage && (
                  <span className={`text-xs ${saveState === 'error' ? 'text-dc-red' : 'text-dc-green'}`}>
                    {saveMessage}
                  </span>
                )}
              </div>
            </form>
          )}
        </>
      )}
    </div>
  )
}

// useSearchParams 需要 Suspense 边界（Next 15 静态渲染要求），与 chat 页同模式
export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsContent />
    </Suspense>
  )
}
