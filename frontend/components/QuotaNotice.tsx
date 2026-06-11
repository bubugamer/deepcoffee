import Link from 'next/link'
import { Zap } from 'lucide-react'

/**
 * AI 额度用尽（402 ai_quota_exceeded）时的引导卡片。
 * 各 AI 调用点共用，替代普通报错红条。
 */
export function QuotaNotice({ message }: { message?: string }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-2xl rounded-tl-sm px-4 py-3 max-w-lg">
      <div className="flex items-start gap-2 text-sm text-amber-800 leading-relaxed">
        <Zap size={14} className="flex-shrink-0 mt-0.5" />
        <span>{message || '本月 AI 问答次数已用完，升级 Pro 可无限使用。'}</span>
      </div>
      <Link
        href="/app/settings"
        className="inline-block mt-2 text-sm font-medium text-dc-accent hover:underline"
      >
        升级 Pro →
      </Link>
    </div>
  )
}
