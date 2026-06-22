import type { UserProfile, UserQuota } from '@/types'

export function normalizedPlan(profile?: Pick<UserProfile, 'plan'> | null): 'basic' | 'pro' | 'max' {
  return profile?.plan === 'pro' || profile?.plan === 'max' ? profile.plan : 'basic'
}

export function isAdmin(profile?: Pick<UserProfile, 'role'> | null): boolean {
  return profile?.role === 'admin'
}

export function canBrowseKnowledge(profile?: Pick<UserProfile, 'plan' | 'role'> | null): boolean {
  return isAdmin(profile) || normalizedPlan(profile) === 'max'
}

export function canUseBeanSquare(profile?: Pick<UserProfile, 'plan' | 'role'> | null): boolean {
  const plan = normalizedPlan(profile)
  return isAdmin(profile) || plan === 'pro' || plan === 'max'
}

export function planLabel(profile?: Pick<UserProfile, 'plan'> | null): string {
  const plan = normalizedPlan(profile)
  if (plan === 'max') return 'Max 版'
  if (plan === 'pro') return 'Pro 版'
  return profile ? 'Basic 版' : '载入中'
}

export function quotaPercent(quota?: Pick<UserQuota, 'ai_used' | 'ai_total'> | null): number {
  if (!quota?.ai_total) return 0
  return Math.min(Math.round((quota.ai_used / quota.ai_total) * 100), 100)
}
