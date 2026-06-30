import type {
  AlipayOrderResponse,
  BillingInterval,
  BillingOrderStatus,
  BillingStatus,
  PaidPlan,
  StripeCheckoutResponse,
} from '@/types'
import { apiFetch } from './client'

export function getBillingStatus(): Promise<BillingStatus> {
  return apiFetch('/billing/status')
}

export function createAlipayOrder(body: { plan: PaidPlan; interval: BillingInterval }): Promise<AlipayOrderResponse> {
  return apiFetch('/billing/alipay/orders', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function queryAlipayOrder(orderId: string): Promise<BillingOrderStatus> {
  return apiFetch(`/billing/alipay/orders/${encodeURIComponent(orderId)}/query`, {
    method: 'POST',
  })
}

export function getBillingOrder(orderId: string): Promise<BillingOrderStatus> {
  return apiFetch(`/billing/orders/${encodeURIComponent(orderId)}`)
}

export function createStripeCheckout(body: { plan: PaidPlan; interval: BillingInterval }): Promise<StripeCheckoutResponse> {
  return apiFetch('/billing/stripe/checkout', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
