'use client'
// 补填邀请码弹窗：后端开启邀请门禁(invite_required)且当前账号未绑定邀请码时，
// 在应用入口处阻断业务操作，引导补码（redeem 成功后回调刷新 profile）。
// 触发条件由 AppLayout 依据 /me 的 invite_bound 字段判断。
import { useState } from 'react'
import { Loader2, KeyRound } from 'lucide-react'
import { redeemInviteCode } from '@/lib/api/user'
import { ApiError } from '@/lib/api/client'

export default function InviteGateModal({ onBound }: { onBound: () => void }) {
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = code.trim().toUpperCase()
    if (!trimmed) { setError('请输入邀请码'); return }
    setSubmitting(true)
    setError(null)
    try {
      await redeemInviteCode(trimmed)
      onBound()
    } catch (err) {
      setError(err instanceof ApiError && err.status === 400
        ? '邀请码无效或已被使用'
        : '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4">
      <div className="dc-card w-full max-w-sm p-7">
        <div className="flex flex-col items-center text-center mb-5">
          <div className="w-12 h-12 rounded-full bg-dc-subtle flex items-center justify-center mb-3">
            <KeyRound size={22} className="text-dc-accent" />
          </div>
          <h2 className="text-base font-bold text-dc-text-1 mb-1">需要邀请码</h2>
          <p className="text-xs text-dc-text-3 leading-relaxed">
            你的账号还未绑定邀请码。输入邀请码完成激活后即可使用全部功能。
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            className="dc-input"
            type="text"
            placeholder="DC-XXXX-XXXX"
            value={code}
            onChange={e => setCode(e.target.value)}
            autoCapitalize="characters"
            autoFocus
          />
          {error && <p className="text-xs text-dc-red">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full py-2.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            激活账号
          </button>
        </form>
      </div>
    </div>
  )
}
