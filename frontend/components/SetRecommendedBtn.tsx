'use client'
import { useState } from 'react'
import { Bookmark, Check, Loader2 } from 'lucide-react'
import { setRecommendedParams } from '@/lib/api/beans'
import { getToken } from '@/lib/auth'

interface Props {
  beanCardId?: string | null
  recordId?: string
}

export default function SetRecommendedBtn({ beanCardId, recordId }: Props) {
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSet() {
    if (!beanCardId || !recordId || saving) return
    setSaving(true)
    setError('')
    try {
      await setRecommendedParams(beanCardId, recordId, getToken())
      setSaved(true)
      setTimeout(() => setSaved(false), 2200)
    } catch (err) {
      setError(err instanceof Error ? err.message : '设置失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  if (!beanCardId) {
    return (
      <span className="flex items-center gap-1.5 text-xs py-1.5 px-3 rounded-lg border border-dc-border text-dc-text-3 bg-dc-subtle">
        未关联豆卡
      </span>
    )
  }

  if (saved) {
    return (
      <span className="flex items-center gap-1.5 text-xs py-1.5 px-3 rounded-lg border border-dc-green bg-dc-green-bg text-dc-green">
        <Check size={12} />
        已设为建议参数
      </span>
    )
  }

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-red-500">{error}</span>}
      <button
        onClick={handleSet}
        disabled={saving || !recordId}
        className="flex items-center gap-1.5 text-xs py-1.5 px-3 rounded-lg border border-dc-border text-dc-text-3 hover:text-dc-text-2 hover:bg-dc-subtle transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {saving ? <Loader2 size={12} className="animate-spin" /> : <Bookmark size={12} />}
        {saving ? '设置中' : '设为建议参数'}
      </button>
    </div>
  )
}
