'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { getBillingOrder, getBillingStatus } from '@/lib/api/billing'
import { getUserProfile } from '@/lib/api/user'
import type { BillingOrderStatus, BillingStatus, UserProfile } from '@/types'

function SuccessContent() {
  const searchParams = useSearchParams()
  const orderId = searchParams.get('order_id')
  const [order, setOrder] = useState<BillingOrderStatus | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!orderId) {
      setError('缺少支付订单号。')
      return
    }
    let cancelled = false
    let attempts = 0
    const load = () => {
      attempts += 1
      Promise.allSettled([getBillingOrder(orderId), getUserProfile(), getBillingStatus()])
        .then(([orderRes, profileRes, billingRes]) => {
          if (cancelled) return
          if (orderRes.status === 'fulfilled') setOrder(orderRes.value)
          else setError(orderRes.reason instanceof Error ? orderRes.reason.message : '支付状态加载失败。')
          if (profileRes.status === 'fulfilled') setProfile(profileRes.value)
          if (billingRes.status === 'fulfilled') setStatus(billingRes.value)
        })
    }
    load()
    const timer = window.setInterval(() => {
      if (cancelled || attempts >= 8 || order?.status === 'paid') {
        window.clearInterval(timer)
        return
      }
      load()
    }, 2500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [orderId, order?.status])

  const paid = order?.status === 'paid'
  const pending = !order || order.status === 'pending'
  const plan = profile?.plan === 'max' ? 'Max' : profile?.plan === 'pro' ? 'Pro' : 'Basic'
  const expiry = status?.plan_expires_at ?? order?.period_end
  const expiryLabel = expiry ? new Date(expiry).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }) : ''

  return (
    <div className="p-4 sm:p-8 max-w-xl mx-auto">
      <div className="dc-card p-8 text-center">
        {paid ? (
          <CheckCircle2 size={44} className="mx-auto text-dc-green mb-4" />
        ) : error ? (
          <XCircle size={44} className="mx-auto text-dc-red mb-4" />
        ) : (
          <Loader2 size={44} className="mx-auto text-dc-accent mb-4 animate-spin" />
        )}
        <h1 className="text-xl font-bold text-dc-text-1 mb-2">
          {paid ? '会员已开通' : error ? '支付状态暂不可用' : '正在确认支付'}
        </h1>
        <p className="text-sm text-dc-text-3 mb-6">
          {paid
            ? `当前套餐为 ${plan}${expiryLabel ? `，有效期至 ${expiryLabel}` : ''}。`
            : pending
              ? '支付平台正在通知 DeepCoffee，请稍候。'
              : error || '订单尚未完成。'}
        </p>
        {order && (
          <div className="rounded-lg bg-dc-subtle text-left text-xs text-dc-text-2 p-4 mb-6 space-y-1">
            <div>订单：<span className="font-mono">{order.id}</span></div>
            <div>渠道：{order.provider === 'stripe' ? 'Stripe' : '支付宝'}</div>
            <div>周期：{order.interval === 'yearly' ? '年付' : '月付'}</div>
            <div>状态：{order.status}</div>
          </div>
        )}
        <Link href="/app/settings?tab=plan" className="btn-primary inline-flex px-5 py-2.5 text-sm">
          返回会员页
        </Link>
      </div>
    </div>
  )
}

export default function BillingSuccessPage() {
  return (
    <Suspense>
      <SuccessContent />
    </Suspense>
  )
}
