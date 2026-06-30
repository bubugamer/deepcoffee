import type { BillingPlan, UserProfile, UserQuota } from '@/types'
import { apiFetch, isApiEnabled } from './client'

// Local fallback for development when NEXT_PUBLIC_API_BASE_URL is not configured.
const fallbackUser: UserProfile = {
  id: 'mock_user_01',
  email: 'user@example.com',
  display_name: '谢明思',
  plan: 'basic',
  timezone: 'Asia/Shanghai',
  unit_system: 'metric',
  created_at: '2026-05-01T00:00:00Z',
}

const fallbackQuota: UserQuota = {
  plan: 'basic',
  balance: 0,
  ai_used: 22,
  ai_total: 99,
  ai_remaining: 77,
  reset_at: '2026-07-01T00:00:00+08:00',
  features: ['基础 AI 用量', '可使用 AI 知识库问答', '可打开 AI 引用文章'],
}

// Pro plan features (shown in the upgrade card)
export const proPlanFeatures: string[] = [
  '更多 AI 用量',
  '可查看同豆匿名冲煮记录',
  '可进入豆仓广场',
  '可打开 AI 引用文章',
]

export const maxPlanFeatures: string[] = [
  '近乎无限 AI 用量',
  '包含 Pro 权益',
  '可自由浏览知识库',
]

// ── API Functions ─────────────────────────────────────────────────────────
// GET /v1/me
export async function getUserProfile(token?: string | null): Promise<UserProfile> {
  if (isApiEnabled) return apiFetch<UserProfile>('/me', { token })
  return fallbackUser
}

// PATCH /v1/me
export async function updateUserProfile(data: {
  display_name?: string
  timezone?: string
  unit_system?: string
}, token?: string | null): Promise<UserProfile> {
  if (isApiEnabled) {
    return apiFetch<UserProfile>('/me', {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    })
  }
  return { ...fallbackUser, ...data }
}

// GET /v1/me/quota
export async function getUserQuota(token?: string | null): Promise<UserQuota> {
  if (isApiEnabled) return apiFetch<UserQuota>('/me/quota', { token })
  return fallbackQuota
}

// GET /v1/billing/plans（公开，无需 token）
export async function getBillingPlans(): Promise<BillingPlan[]> {
  if (isApiEnabled) {
    return apiFetch('/billing/plans')
  }
  return [
    { id: 'basic', name: 'Basic', price: 0, currency: 'CNY', token_limit: 0, request_limit: 99, period: 'month', features: fallbackQuota.features },
    {
      id: 'pro',
      name: 'Pro',
      price: 59,
      currency: 'CNY',
      token_limit: null,
      request_limit: 500,
      period: 'month',
      features: proPlanFeatures,
      prices: {
        monthly: { amount: 59, currency: 'CNY', interval: 'monthly', display: '59 元/月' },
        yearly: { amount: 568, currency: 'CNY', interval: 'yearly', display: '568 元/年' },
      },
    },
    {
      id: 'max',
      name: 'Max',
      price: 99,
      currency: 'CNY',
      token_limit: null,
      request_limit: 1000,
      period: 'month',
      features: maxPlanFeatures,
      prices: {
        monthly: { amount: 99, currency: 'CNY', interval: 'monthly', display: '99 元/月' },
        yearly: { amount: 938, currency: 'CNY', interval: 'yearly', display: '938 元/年' },
      },
    },
  ]
}

// POST /v1/invites/validate（公开，无需 token）
export async function validateInviteCode(code: string): Promise<{ valid: boolean; message: string }> {
  return apiFetch('/invites/validate', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

// POST /v1/invites/redeem — 注册拿到 token 后必须主动调用一次，否则邀请码不会被标记为已用。
// 失败时返回 400 invite_invalid（如该码刚被他人用掉）。
export async function redeemInviteCode(code: string, token?: string | null): Promise<{ redeemed: boolean; message: string }> {
  return apiFetch('/invites/redeem', {
    method: 'POST',
    token,
    body: JSON.stringify({ code }),
  })
}
