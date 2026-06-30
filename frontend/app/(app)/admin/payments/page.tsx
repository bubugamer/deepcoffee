'use client'

import { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { listAdminPayments, type AdminPaymentOrder } from '@/lib/api/admin'

const PAGE_SIZE = 50

function statusLabel(status: string): string {
  return {
    pending: '待支付',
    paid: '已支付',
    expired: '已过期',
    canceled: '已取消',
    failed: '失败',
  }[status] ?? status
}

export default function AdminPaymentsPage() {
  const [items, setItems] = useState<AdminPaymentOrder[] | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    setError('')
    listAdminPayments(page, PAGE_SIZE)
      .then(setItems)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [page])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-dc-text-1">支付记录</h1>
        <p className="text-sm text-dc-text-3 mt-1">支付宝订单和 Stripe 订阅结账记录会在这里汇总。</p>
      </div>

      {error && <div className="text-sm text-dc-red">{error}</div>}

      <div className="dc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-dc-text-3 border-b border-dc-border">
              <th className="px-4 py-3 font-medium">用户</th>
              <th className="px-4 py-3 font-medium">渠道</th>
              <th className="px-4 py-3 font-medium">套餐</th>
              <th className="px-4 py-3 font-medium">金额</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">有效期</th>
              <th className="px-4 py-3 font-medium">创建时间</th>
              <th className="px-4 py-3 font-medium">外部单号</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dc-border">
            {items === null && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-dc-text-3">
                  <Loader2 size={15} className="animate-spin inline mr-2" />加载中…
                </td>
              </tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-dc-text-3">暂无支付记录</td></tr>
            )}
            {items?.map(item => (
              <tr key={item.id}>
                <td className="px-4 py-3 max-w-56">
                  <div className="truncate text-dc-text-1">{item.user_email ?? item.user_id}</div>
                  <div className="font-mono text-[11px] text-dc-text-3 truncate">{item.id}</div>
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-2">{item.provider === 'stripe' ? 'Stripe' : '支付宝'}</td>
                <td className="px-4 py-3 text-xs text-dc-text-2 whitespace-nowrap">
                  {item.plan} · {item.interval === 'yearly' ? '年付' : '月付'}
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-2 whitespace-nowrap">
                  {item.amount > 0 ? `${item.currency} ${item.amount}` : item.currency}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    item.status === 'paid' ? 'bg-green-50 text-dc-green' : item.status === 'pending' ? 'bg-yellow-50 text-dc-yellow' : 'bg-red-50 text-dc-red'
                  }`}>
                    {statusLabel(item.status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-3 whitespace-nowrap">
                  {item.period_end ? new Date(item.period_end).toLocaleDateString('zh-CN') : '—'}
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-3 whitespace-nowrap">
                  {new Date(item.created_at).toLocaleString('zh-CN')}
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-dc-text-3 max-w-52 truncate">
                  {item.external_transaction_id ?? item.external_order_id ?? item.external_subscription_id ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2 text-sm">
        <button
          disabled={page <= 1}
          onClick={() => setPage(p => p - 1)}
          className="p-1.5 text-dc-text-3 hover:text-dc-text-1 disabled:opacity-40"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-xs text-dc-text-3">第 {page} 页</span>
        <button
          disabled={(items?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage(p => p + 1)}
          className="p-1.5 text-dc-text-3 hover:text-dc-text-1 disabled:opacity-40"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}
