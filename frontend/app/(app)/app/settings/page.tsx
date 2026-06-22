'use client'
import { FormEvent, Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Check } from 'lucide-react'
import { getBillingPlans, getUserProfile, getUserQuota, maxPlanFeatures, proPlanFeatures, updateUserProfile } from '@/lib/api/user'
import { getToken } from '@/lib/auth'
import { planLabel as displayPlanLabel, quotaPercent as calcQuotaPercent } from '@/lib/entitlements'
import type { BillingPlan, UserProfile, UserQuota } from '@/types'

type Tab = 'profile' | 'plan' | 'prefs'
type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const TABS: Tab[] = ['profile', 'plan', 'prefs']

function SettingsContent() {
  // 支持 ?tab=plan 直达「配额与会员」（侧边栏「升级会员」入口用）
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
    Promise.all([getUserProfile(token), getUserQuota(token)])
      .then(([nextProfile, nextQuota]) => {
        if (cancelled) return
        setProfile(nextProfile)
        setQuota(nextQuota)
        setDisplayName(nextProfile.display_name ?? '')
        setTimezone(nextProfile.timezone || 'Asia/Shanghai')
        setUnitSystem(nextProfile.unit_system === 'imperial' ? 'imperial' : 'metric')
      })
      .catch((error) => {
        if (cancelled) return
        setLoadError(error instanceof Error ? error.message : '设置加载失败，请稍后重试。')
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
            <form onSubmit={saveProfile} className="dc-card p-6 space-y-5 max-w-lg">
              <div className="flex items-center gap-4 pb-5 border-b border-dc-border">
                <div className="w-14 h-14 rounded-full bg-dc-accent flex items-center justify-center text-white text-xl font-bold">{initial}</div>
                <div>
                  <div className="font-semibold text-dc-text-1">{displayName || profile.email}</div>
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
              </div>
              <div>
                <label className="text-xs text-dc-text-3 mb-1.5 block">邮箱</label>
                <input className="dc-input" value={profile.email ?? ''} readOnly />
              </div>
              <div>
                <label className="text-xs text-dc-text-3 mb-1.5 block">密码</label>
                <button type="button" className="btn-secondary text-sm px-4 py-2">修改密码</button>
              </div>
              <div className="pt-2 flex items-center gap-3">
                <button className="btn-primary text-sm px-5 py-2" disabled={saveState === 'saving'}>
                  {saveState === 'saving' ? '保存中…' : '保存修改'}
                </button>
                {saveMessage && (
                  <span className={`text-xs ${saveState === 'error' ? 'text-dc-red' : 'text-dc-green'}`}>
                    {saveMessage}
                  </span>
                )}
              </div>
            </form>
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
                      记录冲煮、豆卡识别和知识库问答统一消耗 AI 问答次数。
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
                  { id: 'basic', title: 'Basic', fallbackPrice: 0, fallbackFeatures: ['AI 问答 99 次 / 月', '可使用 AI 知识库问答', '可打开 AI 引用文章'] },
                  { id: 'pro', title: 'Pro', fallbackPrice: 59, fallbackFeatures: proPlanFeatures },
                  { id: 'max', title: 'Max', fallbackPrice: 99, fallbackFeatures: maxPlanFeatures },
                ].map((plan) => {
                  const apiPlan = plans.find((item) => item.id === plan.id)
                  const active = profile.plan === plan.id
                  return (
                    <div key={plan.id} className={`dc-card p-6 ${active ? 'border-dc-accent ring-1 ring-dc-accent/20' : ''}`}>
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="section-title">{plan.title} 版</h2>
                        {active && <span className="dc-tag-accent">当前套餐</span>}
                      </div>
                      <div className="text-3xl font-extrabold text-dc-text-1 mb-1">
                        ¥{apiPlan?.price ?? plan.fallbackPrice} <span className="text-sm font-normal text-dc-text-3">/ 月</span>
                      </div>
                      <p className="text-xs text-dc-text-3 mb-5">{plan.id === 'basic' ? '免费使用' : '支付暂未开放，可联系管理员开通'}</p>
                      <ul className="space-y-2.5 mb-5">
                        {(apiPlan?.features ?? plan.fallbackFeatures).map(f => (
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
