'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, MessageSquare } from 'lucide-react'
import { BeanForm, emptyBeanFormValue, type BeanFormValue } from '@/components/BeanForm'
import { confirmBean, getBeans, getBeanEntityCatalog, type BeanEntityCatalog } from '@/lib/api/beans'
import { beanFieldSuggestions, draftToComponent, normalizedComponentsForSave, validateComponentsForSave } from '@/lib/beans'
import { getToken } from '@/lib/auth'
import type { Bean, BeanDraft } from '@/types'

const EMPTY_CATALOG: BeanEntityCatalog = { roaster: [], process: [], origin: [], varietal: [] }

function splitNotes(text: string): string[] {
  return text.split(/[，,]/).map((s) => s.trim()).filter(Boolean)
}

export default function NewBeanPage() {
  const router = useRouter()
  const [beans, setBeans] = useState<Bean[]>([])
  const [catalog, setCatalog] = useState<BeanEntityCatalog>(EMPTY_CATALOG)
  const [value, setValue] = useState<BeanFormValue>(() => emptyBeanFormValue())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const token = getToken()
    getBeans({}, token)
      .then((items) => { if (!cancelled) setBeans(items) })
      .catch(() => {})
    getBeanEntityCatalog(token)
      .then((c) => { if (!cancelled) setCatalog(c) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const suggestions = useMemo(() => beanFieldSuggestions(beans, catalog), [beans, catalog])

  async function save() {
    if (!value.fields.roaster_name?.trim()) {
      setError('请填写烘焙商。')
      return
    }
    const componentError = validateComponentsForSave(value.components)
    if (componentError) {
      setError(componentError)
      return
    }
    setSaving(true)
    setError('')
    try {
      const token = getToken()
      const flavorNotes = splitNotes(value.flavorNotesText)
      const axes = value.axes.filter((a) => a.label.trim()).map((a) => ({ label: a.label.trim(), value: a.value ?? null }))
      const draft: BeanDraft = {
        roaster_name: value.fields.roaster_name.trim() || undefined,
        roaster_product_name: value.fields.roaster_product_name?.trim() || undefined,
        roast_date_text: value.fields.roast_date_text?.trim() || undefined,
        net_weight_text: value.fields.net_weight_text?.trim() || undefined,
        bean_components: normalizedComponentsForSave(value.components).map(draftToComponent),
        flavor: flavorNotes.length || axes.length
          ? { notes: flavorNotes, source: 'roaster', scale_max: 5, axes }
          : undefined,
      }
      const res = await confirmBean(draft, undefined, token, 'form')
      router.push(`/app/beans/${res.bean_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-3xl mx-auto">
      <Link href="/app/beans" className="flex items-center gap-1.5 text-sm text-dc-text-3 hover:text-dc-accent mb-6 w-fit">
        <ArrowLeft size={15} />
        返回豆仓
      </Link>

      <div className="flex items-center justify-between gap-4 mb-6">
        <h1 className="text-xl font-bold text-dc-text-1">新建豆卡</h1>
        <Link href="/app/chat?new=bean" className="text-sm py-2 px-3.5 flex items-center gap-1.5 rounded-lg border border-dc-accent text-dc-accent font-medium hover:bg-dc-accent-light transition-colors">
          <MessageSquare size={16} />
          AI 对话新增
        </Link>
      </div>

      <div>
        {error && <div className="mb-4 text-sm text-dc-red bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>}

        <BeanForm value={value} onChange={setValue} suggestions={suggestions} />

        <div className="flex gap-2 mt-6">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="btn-primary text-sm py-2 px-5 disabled:opacity-50 flex items-center gap-2"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {saving ? '保存中…' : '保存豆卡'}
          </button>
          <button type="button" onClick={() => router.push('/app/beans')} disabled={saving} className="btn-secondary text-sm py-2 px-5">
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
