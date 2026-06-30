'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, MessageSquare } from 'lucide-react'
import { BrewRecordForm, type BrewRecordFormSubmit } from '@/components/BrewRecordForm'
import { getBeans } from '@/lib/api/beans'
import { createEquipment, listEquipment, type EquipmentProfile } from '@/lib/api/equipment'
import { createRecord } from '@/lib/api/records'
import { getToken } from '@/lib/auth'
import type { Bean } from '@/types'

export default function NewBrewRecordPage() {
  const router = useRouter()
  const [beans, setBeans] = useState<Bean[]>([])
  const [equipment, setEquipment] = useState<EquipmentProfile[]>([])
  const [preferredBeanId, setPreferredBeanId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setPreferredBeanId(new URLSearchParams(window.location.search).get('bean_id'))
    let cancelled = false
    const token = getToken()
    Promise.all([getBeans({}, token), listEquipment()])
      .then(([nextBeans, nextEquipment]) => {
        if (cancelled) return
        setBeans(nextBeans)
        setEquipment(nextEquipment)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '页面加载失败，请稍后重试。')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  async function save(value: BrewRecordFormSubmit) {
    setSaving(true)
    setError('')
    try {
      const token = getToken()
      for (const item of value.equipmentToUpsert) {
        await createEquipment(item)
      }
      const created = await createRecord(value.payload, token)
      router.push(`/app/records/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <Link href="/app/records" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
        <ArrowLeft size={15} />
        返回记录
      </Link>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-dc-text-1 mb-1">新建冲煮记录</h1>
          <p className="text-sm text-dc-text-3">通过表单新增不会消耗 AI 额度。</p>
        </div>
        <Link href="/app/chat?new=1" className="btn-secondary text-sm py-2 flex items-center gap-1.5">
          <MessageSquare size={14} />
          AI 对话新增
        </Link>
      </div>

      {loading ? (
        <div className="dc-card p-6 text-sm text-dc-text-3">正在加载豆仓和器具…</div>
      ) : beans.length === 0 ? (
        <div className="dc-card p-6">
          <h2 className="text-sm font-semibold text-dc-text-1 mb-2">需要先有一张豆卡</h2>
          <p className="text-sm text-dc-text-3 mb-4">冲煮记录必须关联豆仓中的一款豆子。</p>
          <Link href="/app/beans/new" className="btn-primary text-sm py-2 inline-flex">去建豆卡</Link>
        </div>
      ) : (
        <div className="max-w-3xl">
          <BrewRecordForm
            mode="create"
            beans={beans}
            equipment={equipment}
            preferredBeanId={preferredBeanId}
            saving={saving}
            error={error}
            onCancel={() => router.push('/app/records')}
            onSubmit={save}
          />
        </div>
      )}
    </div>
  )
}
