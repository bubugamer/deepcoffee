'use client'
// 邀请码管理：列表（状态筛选 + 使用者邮箱）/ 批量生成 / 复制 / 作废。
import { useCallback, useEffect, useState } from 'react'
import { Loader2, Plus, Copy, Check, Ban } from 'lucide-react'
import {
  listInvites, createInvites, revokeInvite, type InviteCodeInfo,
} from '@/lib/api/admin'
import { ApiError } from '@/lib/api/client'

const statusFilters = [
  { value: '',        label: '全部' },
  { value: 'active',  label: '可用' },
  { value: 'used',    label: '已用' },
  { value: 'revoked', label: '已作废' },
]

const statusBadge: Record<string, string> = {
  active: 'bg-green-50 text-dc-green',
  used: 'bg-dc-subtle text-dc-text-3',
  revoked: 'bg-red-50 text-dc-red',
}

export default function AdminInvitesPage() {
  const [items, setItems] = useState<InviteCodeInfo[] | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  // 生成对话框
  const [showCreate, setShowCreate] = useState(false)
  const [count, setCount] = useState(5)
  const [note, setNote] = useState('')
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<InviteCodeInfo[] | null>(null)

  const refresh = useCallback(() => {
    setError(null)
    listInvites(filter || undefined)
      .then(setItems)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [filter])

  useEffect(() => { refresh() }, [refresh])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    try {
      const rows = await createInvites({ count, note: note.trim() || undefined })
      setCreated(rows)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成失败')
    } finally {
      setCreating(false)
    }
  }

  async function handleRevoke(code: string) {
    if (!window.confirm(`确认作废邀请码 ${code}？作废后不可恢复。`)) return
    try {
      await revokeInvite(code)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError && err.code === 'invite_already_used'
        ? '该码已被使用，无法作废'
        : err instanceof Error ? err.message : '作废失败')
    }
  }

  function copy(text: string, key: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key)
      setTimeout(() => setCopied(null), 1500)
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1 bg-dc-subtle rounded-lg p-1">
          {statusFilters.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filter === f.value ? 'bg-white text-dc-text-1 shadow-sm' : 'text-dc-text-3 hover:text-dc-text-1'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => { setShowCreate(true); setCreated(null) }}
          className="btn-primary px-4 py-2 text-sm flex items-center gap-1.5"
        >
          <Plus size={14} /> 生成邀请码
        </button>
      </div>

      {error && <div className="text-sm text-dc-red">{error}</div>}

      <div className="dc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-dc-text-3 border-b border-dc-border">
              <th className="px-4 py-3 font-medium">邀请码</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">使用者</th>
              <th className="px-4 py-3 font-medium">备注</th>
              <th className="px-4 py-3 font-medium">创建时间</th>
              <th className="px-4 py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dc-border">
            {items === null && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-dc-text-3">
                <Loader2 size={15} className="animate-spin inline mr-2" />加载中…
              </td></tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-dc-text-3">暂无邀请码</td></tr>
            )}
            {items?.map(row => (
              <tr key={row.code}>
                <td className="px-4 py-3 font-mono text-dc-text-1">{row.code}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge[row.status] ?? 'bg-dc-subtle text-dc-text-3'}`}>
                    {row.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-dc-text-2">{row.used_by_email ?? '—'}</td>
                <td className="px-4 py-3 text-dc-text-3 max-w-40 truncate">{row.note ?? '—'}</td>
                <td className="px-4 py-3 text-xs text-dc-text-3">{new Date(row.created_at).toLocaleString('zh-CN')}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {row.status === 'active' && (
                    <>
                      <button
                        onClick={() => copy(row.code, row.code)}
                        className="p-1.5 text-dc-text-3 hover:text-dc-accent"
                        title="复制"
                      >
                        {copied === row.code ? <Check size={14} className="text-dc-green" /> : <Copy size={14} />}
                      </button>
                      <button
                        onClick={() => handleRevoke(row.code)}
                        className="p-1.5 text-dc-text-3 hover:text-dc-red"
                        title="作废"
                      >
                        <Ban size={14} />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 生成对话框 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={() => setShowCreate(false)}>
          <div className="dc-card w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-bold text-dc-text-1 mb-4">生成邀请码</h3>
            {created ? (
              <div className="space-y-3">
                <div className="bg-dc-subtle rounded-lg p-3 space-y-1 max-h-48 overflow-y-auto">
                  {created.map(c => (
                    <div key={c.code} className="font-mono text-sm text-dc-text-1">{c.code}</div>
                  ))}
                </div>
                <button
                  onClick={() => copy(created.map(c => c.code).join('\n'), '__all__')}
                  className="btn-primary w-full py-2.5 text-sm flex items-center justify-center gap-1.5"
                >
                  {copied === '__all__' ? <Check size={14} /> : <Copy size={14} />}
                  复制全部
                </button>
                <button onClick={() => setShowCreate(false)} className="w-full py-2 text-sm text-dc-text-3 hover:text-dc-text-1">
                  关闭
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="text-xs text-dc-text-3 mb-1.5 block">数量（1–100）</label>
                  <input
                    className="dc-input" type="number" min={1} max={100} value={count}
                    onChange={e => setCount(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
                  />
                </div>
                <div>
                  <label className="text-xs text-dc-text-3 mb-1.5 block">备注（可选）</label>
                  <input
                    className="dc-input" type="text" placeholder="如：beta batch 2" maxLength={200}
                    value={note} onChange={e => setNote(e.target.value)}
                  />
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setShowCreate(false)} className="flex-1 py-2.5 text-sm text-dc-text-3 hover:text-dc-text-1 border border-dc-border rounded-lg">
                    取消
                  </button>
                  <button type="submit" disabled={creating} className="flex-1 btn-primary py-2.5 text-sm disabled:opacity-60 flex items-center justify-center gap-2">
                    {creating && <Loader2 size={14} className="animate-spin" />}
                    生成
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
