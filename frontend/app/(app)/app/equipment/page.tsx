'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Coffee, Loader2, Pencil, Plus, Star, Trash2 } from 'lucide-react'
import {
  createEquipment,
  deleteEquipment,
  getEquipmentCatalog,
  listEquipment,
  setDefaultEquipment,
  updateEquipment,
  type EquipmentCategory,
  type EquipmentInput,
  type EquipmentProfile,
} from '@/lib/api/equipment'

const CATEGORY_META: Record<EquipmentCategory, { label: string; placeholder: string }> = {
  brewer: { label: '冲煮器具', placeholder: '如：V60 01 / 法压壶 / 爱乐压' },
  grinder: { label: '磨豆机', placeholder: '如：ZP6S / Comandante C40' },
  filter_media: { label: '过滤介质', placeholder: '如：纸滤 / 金属滤网' },
  water: { label: '用水', placeholder: '如：农夫山泉 / 自配水' },
}

const CATEGORIES = Object.keys(CATEGORY_META) as EquipmentCategory[]
const CUSTOM = '__custom__'

function EquipmentForm({
  initial, saving, onSubmit, onCancel,
}: {
  initial: EquipmentInput
  saving: boolean
  onSubmit: (values: EquipmentInput) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<EquipmentInput>({ category: 'brewer', ...initial })
  const [catalog, setCatalog] = useState<Record<string, string[]>>({})
  const [customMode, setCustomMode] = useState(false)
  const category = values.category ?? 'brewer'
  const hasName = !!values.name?.trim()

  useEffect(() => {
    let cancelled = false
    getEquipmentCatalog().then(c => { if (!cancelled) setCatalog(c) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  // 名称 = 公共器具目录（按所选类别）；用户也可「自定义输入」兜底。
  const nameValue = values.name ?? ''
  const nameOptions = catalog[category] ?? []
  const isCustomName = nameValue.trim() !== '' && !nameOptions.includes(nameValue)
  const showNameInput = customMode || isCustomName

  return (
    <form
      onSubmit={e => { e.preventDefault(); if (hasName) onSubmit(values) }}
      className="grid md:grid-cols-[160px_1fr_1fr_auto] gap-3 items-end"
    >
      <label className="block">
        <span className="text-xs text-dc-text-3 mb-1 block">类别</span>
        <select
          className="dc-input text-sm"
          value={category}
          onChange={e => setValues(cur => ({ ...cur, category: e.target.value as EquipmentCategory }))}
        >
          {CATEGORIES.map(c => <option key={c} value={c}>{CATEGORY_META[c].label}</option>)}
        </select>
      </label>
      <label className="block">
        <span className="text-xs text-dc-text-3 mb-1 block">名称</span>
        <select
          className="dc-input text-sm"
          value={showNameInput ? CUSTOM : nameValue}
          onChange={e => {
            const v = e.target.value
            if (v === CUSTOM) {
              setCustomMode(true)
            } else {
              setCustomMode(false)
              setValues(cur => ({ ...cur, name: v }))
            }
          }}
        >
          <option value="">未选择</option>
          {nameOptions.map(n => <option key={n} value={n}>{n}</option>)}
          <option value={CUSTOM}>自定义输入…</option>
        </select>
        {showNameInput && (
          <input
            className="dc-input text-sm mt-1.5"
            value={nameValue}
            placeholder={CATEGORY_META[category].placeholder}
            maxLength={120}
            onChange={e => setValues(cur => ({ ...cur, name: e.target.value }))}
          />
        )}
      </label>
      <label className="block">
        <span className="text-xs text-dc-text-3 mb-1 block">备注</span>
        <input
          className="dc-input text-sm"
          value={values.notes ?? ''}
          placeholder="可选"
          maxLength={500}
          onChange={e => setValues(cur => ({ ...cur, notes: e.target.value }))}
        />
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving || !hasName}
          className="btn-primary text-sm py-2 px-4 disabled:opacity-50 flex items-center gap-1.5"
        >
          {saving && <Loader2 size={13} className="animate-spin" />}
          保存
        </button>
        <button type="button" onClick={onCancel} className="text-sm py-2 px-3 text-dc-text-3 hover:text-dc-text-1">
          取消
        </button>
      </div>
    </form>
  )
}

export default function EquipmentPage() {
  const [items, setItems] = useState<EquipmentProfile[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(() => {
    setError(null)
    listEquipment().then(setItems).catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const grouped = useMemo(() => {
    const byCategory = Object.fromEntries(CATEGORIES.map(c => [c, [] as EquipmentProfile[]])) as Record<EquipmentCategory, EquipmentProfile[]>
    for (const item of items ?? []) byCategory[item.category].push(item)
    return byCategory
  }, [items])

  async function handleCreate(values: EquipmentInput) {
    setSaving(true)
    try {
      await createEquipment(values)
      setAdding(false)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleUpdate(id: string, values: EquipmentInput) {
    setSaving(true)
    try {
      await updateEquipment(id, values)
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleSetDefault(item: EquipmentProfile) {
    try {
      await setDefaultEquipment(item.id)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '设置失败')
    }
  }

  async function handleDelete(item: EquipmentProfile) {
    if (!window.confirm(`删除「${item.name}」？`)) return
    try {
      await deleteEquipment(item.id)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-content mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-dc-text-1">我的器具</h1>
        {!adding && (
          <button onClick={() => { setAdding(true); setEditingId(null) }} className="btn-primary px-4 py-2 text-sm flex items-center gap-1.5">
            <Plus size={14} /> 添加器具
          </button>
        )}
      </div>

      <p className="text-sm text-dc-text-3 mb-6 leading-relaxed">
        器具按单件保存。Coffea 生成建议时会优先使用每个类别的默认项。
      </p>

      {error && <div className="text-sm text-dc-red mb-4">{error}</div>}

      {adding && (
        <div className="dc-card p-5 mb-4">
          <h3 className="text-sm font-semibold text-dc-text-1 mb-3">添加器具</h3>
          <EquipmentForm initial={{}} saving={saving} onSubmit={handleCreate} onCancel={() => setAdding(false)} />
        </div>
      )}

      {items === null && (
        <div className="flex items-center text-dc-text-3 text-sm py-10 justify-center">
          <Loader2 size={15} className="animate-spin mr-2" />加载中…
        </div>
      )}

      {items?.length === 0 && !adding && (
        <div className="dc-card px-6 py-12 text-center">
          <Coffee size={28} className="text-dc-text-3 mx-auto mb-3" />
          <p className="text-sm text-dc-text-2 mb-1">还没有保存的器具</p>
          <p className="text-xs text-dc-text-3">点右上角「添加器具」，或在对话里让 Coffea 识别后确认保存。</p>
        </div>
      )}

      <div className="space-y-6">
        {CATEGORIES.map(category => (
          <section key={category}>
            <h2 className="text-sm font-semibold text-dc-text-1 mb-2">{CATEGORY_META[category].label}</h2>
            <div className="space-y-3">
              {grouped[category].length === 0 && items !== null && (
                <div className="dc-card px-4 py-3 text-sm text-dc-text-3">暂无{CATEGORY_META[category].label}</div>
              )}
              {grouped[category].map(item => (
                <div key={item.id} className="dc-card p-5">
                  {editingId === item.id ? (
                    <EquipmentForm
                      initial={{ category: item.category, name: item.name, notes: item.notes ?? '' }}
                      saving={saving}
                      onSubmit={values => handleUpdate(item.id, values)}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <div className="flex items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-semibold text-dc-text-1">{item.name}</span>
                          {item.is_default && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-dc-accent/10 text-dc-accent flex items-center gap-1">
                              <Star size={10} fill="currentColor" /> 默认
                            </span>
                          )}
                        </div>
                        {item.notes && <p className="text-sm text-dc-text-3">{item.notes}</p>}
                      </div>
                      <div className="flex gap-1 flex-shrink-0">
                        {!item.is_default && (
                          <button onClick={() => handleSetDefault(item)} className="p-2 text-dc-text-3 hover:text-dc-accent" title="设为默认">
                            <Star size={14} />
                          </button>
                        )}
                        <button onClick={() => { setEditingId(item.id); setAdding(false) }} className="p-2 text-dc-text-3 hover:text-dc-accent" title="编辑">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => handleDelete(item)} className="p-2 text-dc-text-3 hover:text-dc-red" title="删除">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
