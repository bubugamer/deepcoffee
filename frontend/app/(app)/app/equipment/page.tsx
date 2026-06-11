'use client'
// 我的器具：查看 / 新增 / 编辑 / 删除器具组合。
// 数据有两个来源：对话中 AI 推荐参数闭环自动保存，以及这里的手动维护。
import { useCallback, useEffect, useState } from 'react'
import { Loader2, Plus, Pencil, Trash2, Coffee, Star } from 'lucide-react'
import {
  listEquipment, createEquipment, updateEquipment, deleteEquipment, setDefaultEquipment,
  type EquipmentProfile, type EquipmentInput,
} from '@/lib/api/equipment'

// 表单只编辑文本字段；is_default 用列表上的「设为默认」按钮维护。
type EquipmentTextField = Exclude<keyof EquipmentInput, 'is_default'>

const FIELDS: { key: EquipmentTextField; label: string; placeholder: string }[] = [
  { key: 'label',        label: '名称备注',  placeholder: '如：日常手冲一套' },
  { key: 'brew_method',  label: '冲煮方式',  placeholder: '如：V60 / 爱乐压 / 法压' },
  { key: 'grinder',      label: '磨豆机',    placeholder: '如：Comandante C40' },
  { key: 'filter_media', label: '过滤介质',  placeholder: '如：纸滤 / 金属滤网' },
  { key: 'water',        label: '用水',      placeholder: '如：农夫山泉 / 自配水' },
]

function EquipmentForm({
  initial, saving, onSubmit, onCancel,
}: {
  initial: EquipmentInput
  saving: boolean
  onSubmit: (values: EquipmentInput) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<EquipmentInput>(initial)
  const hasContent = Object.values(values).some(v => v?.trim())
  return (
    <form
      onSubmit={e => { e.preventDefault(); if (hasContent) onSubmit(values) }}
      className="space-y-3"
    >
      <div className="grid sm:grid-cols-2 gap-3">
        {FIELDS.map(({ key, label, placeholder }) => (
          <label key={key} className="block">
            <span className="text-xs text-dc-text-3 mb-1 block">{label}</span>
            <input
              className="dc-input text-sm"
              value={values[key] ?? ''}
              placeholder={placeholder}
              maxLength={120}
              onChange={e => setValues(cur => ({ ...cur, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving || !hasContent}
          className="btn-primary text-sm py-2 px-5 disabled:opacity-50 flex items-center gap-2"
        >
          {saving && <Loader2 size={13} className="animate-spin" />}
          保存
        </button>
        <button type="button" onClick={onCancel} className="text-sm py-2 px-4 text-dc-text-3 hover:text-dc-text-1">
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
    const name = item.label || item.brew_method || '这套器具'
    if (!window.confirm(`删除「${name}」？`)) return
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
        在对话里向 Coffea 描述器具（比如请它推荐冲煮参数）时，识别到的器具会自动保存到这里；也可以手动添加和修改。
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
          <p className="text-xs text-dc-text-3">点右上角「添加器具」，或在对话里让 Coffea 推荐冲煮参数时自动记录。</p>
        </div>
      )}

      <div className="space-y-3">
        {items?.map(item => (
          <div key={item.id} className="dc-card p-5">
            {editingId === item.id ? (
              <EquipmentForm
                initial={{
                  label: item.label ?? '',
                  brew_method: item.brew_method ?? '',
                  grinder: item.grinder ?? '',
                  filter_media: item.filter_media ?? '',
                  water: item.water ?? '',
                }}
                saving={saving}
                onSubmit={values => handleUpdate(item.id, values)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-semibold text-dc-text-1">
                      {item.label || item.brew_method || '未命名器具'}
                    </span>
                    {item.is_default && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-dc-accent/10 text-dc-accent flex items-center gap-1">
                        <Star size={10} fill="currentColor" /> 默认
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-dc-text-2">
                    {item.brew_method  && <span><span className="text-dc-text-3 text-xs mr-1.5">冲煮</span>{item.brew_method}</span>}
                    {item.grinder      && <span><span className="text-dc-text-3 text-xs mr-1.5">磨豆机</span>{item.grinder}</span>}
                    {item.filter_media && <span><span className="text-dc-text-3 text-xs mr-1.5">滤材</span>{item.filter_media}</span>}
                    {item.water        && <span><span className="text-dc-text-3 text-xs mr-1.5">用水</span>{item.water}</span>}
                  </div>
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
    </div>
  )
}
