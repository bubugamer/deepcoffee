'use client'
import { FormEvent, useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { getBillingPlans, getUserProfile, getUserQuota, proPlanFeatures, updateUserProfile } from '@/lib/api/user'
import { getToken } from '@/lib/auth'
import type { BillingPlan, UserProfile, UserQuota } from '@/types'

type Tab = 'profile' | 'plan' | 'prefs'
type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [quota, setQuota] = useState<UserQuota | null>(null)
  const [proPlan, setProPlan] = useState<BillingPlan | null>(null)
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
        if (!cancelled) setProPlan(plans.find((p) => p.id === 'pro') ?? null)
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
  const planLabel = profile?.plan === 'pro' ? '会员版' : '免费版'
  const joinedAt = profile?.created_at ? profile.created_at.slice(0, 7) : '--'
  const isUnlimited = quota?.ai_total === null
  const quotaPercent = quota && !isUnlimited && quota.ai_total
    ? Math.round((quota.ai_used / quota.ai_total) * 100)
    : 0
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
                          {quota.ai_used}
                          {' '}
                          <span className="text-dc-text-3 font-normal">
                            / {isUnlimited ? '无限制' : quota.ai_total}
                          </span>
                        </span>
                      </div>
                      {!isUnlimited && (
                        <div className="h-2 bg-dc-subtle rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${quotaPercent > 80 ? 'bg-dc-yellow' : 'bg-dc-accent'}`}
                            style={{ width: `${Math.min(quotaPercent, 100)}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-dc-text-3">
                      记录冲煮和知识库问答统一消耗 AI 问答次数；知识库文章浏览不消耗次数。
                    </p>
                    {resetDate && (
                      <p className="text-xs text-dc-text-3">配额于 {resetDate} 重置</p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-dc-text-3">配额信息暂时不可用。</p>
                )}
              </div>

              {/* Upgrade card */}
              <div className="dc-card p-6 border-dc-accent ring-1 ring-dc-accent/20">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="section-title">会员版</h2>
                  <span className="dc-tag-accent">推荐</span>
                </div>
                <div className="text-3xl font-extrabold text-dc-text-1 mb-1">
                  ¥{proPlan?.price ?? 19} <span className="text-sm font-normal text-dc-text-3">/ 月</span>
                </div>
                <p className="text-xs text-dc-text-3 mb-5">随时取消，无最低承诺</p>
                <ul className="space-y-2.5 mb-5">
                  {(proPlan?.features ?? proPlanFeatures).map(f => (
                    <li key={f} className="flex items-center gap-2 text-sm text-dc-text-2">
                      <Check size={13} className="text-dc-accent flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <button className="btn-primary w-full py-3 text-sm">立即升级</button>
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
