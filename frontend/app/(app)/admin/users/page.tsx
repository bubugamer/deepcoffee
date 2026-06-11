'use client'
// 用户管理：分页列表 + 行内操作（改套餐 / 任免管理员 / 禁用恢复 / 修复计费）。
// 自我降级/自禁用由后端 cannot_modify_self 拦截，前端直接透出报错信息。
import { useCallback, useEffect, useState } from 'react'
import { Loader2, ChevronLeft, ChevronRight, Wrench } from 'lucide-react'
import {
  listAdminUsers, updateAdminUser, repairBillingLink, type AdminUserInfo,
} from '@/lib/api/admin'
import { ApiError } from '@/lib/api/client'

const PAGE_SIZE = 20

export default function AdminUsersPage() {
  const [items, setItems] = useState<AdminUserInfo[] | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // user id 正在操作

  const refresh = useCallback(() => {
    setError(null)
    listAdminUsers(page, PAGE_SIZE)
      .then(setItems)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [page])

  useEffect(() => { refresh() }, [refresh])

  async function mutate(userId: string, body: { plan?: string; role?: string; status?: string }, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(userId)
    setError(null)
    try {
      await updateAdminUser(userId, body)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError && err.code === 'cannot_modify_self'
        ? '不能对自己执行该操作'
        : err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(null)
    }
  }

  async function repair(userId: string) {
    if (!window.confirm('重建该用户的 new-api 计费映射？')) return
    setBusy(userId)
    setError(null)
    try {
      const result = await repairBillingLink(userId)
      window.alert(`修复结果：${result.status ?? 'ok'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '修复失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && <div className="text-sm text-dc-red">{error}</div>}

      <div className="dc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-dc-text-3 border-b border-dc-border">
              <th className="px-4 py-3 font-medium">邮箱</th>
              <th className="px-4 py-3 font-medium">套餐</th>
              <th className="px-4 py-3 font-medium">角色</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">注册邀请码</th>
              <th className="px-4 py-3 font-medium">注册时间</th>
              <th className="px-4 py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dc-border">
            {items === null && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-dc-text-3">
                <Loader2 size={15} className="animate-spin inline mr-2" />加载中…
              </td></tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-dc-text-3">暂无用户</td></tr>
            )}
            {items?.map(u => (
              <tr key={u.id} className={u.status === 'disabled' ? 'opacity-50' : ''}>
                <td className="px-4 py-3 text-dc-text-1 max-w-52 truncate">{u.email ?? u.id}</td>
                <td className="px-4 py-3">
                  <select
                    value={u.plan}
                    disabled={busy === u.id}
                    onChange={e => mutate(u.id, { plan: e.target.value })}
                    className="text-xs border border-dc-border rounded-md px-1.5 py-1 bg-white"
                  >
                    <option value="basic">basic</option>
                    <option value="pro">pro</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  <select
                    value={u.role}
                    disabled={busy === u.id}
                    onChange={e => mutate(u.id, { role: e.target.value },
                      e.target.value === 'admin' ? `将 ${u.email ?? u.id} 设为管理员？` : `撤销 ${u.email ?? u.id} 的管理员权限？`)}
                    className="text-xs border border-dc-border rounded-md px-1.5 py-1 bg-white"
                  >
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  <button
                    disabled={busy === u.id}
                    onClick={() => mutate(
                      u.id,
                      { status: u.status === 'disabled' ? 'active' : 'disabled' },
                      u.status === 'disabled' ? `恢复 ${u.email ?? u.id}？` : `禁用 ${u.email ?? u.id}？禁用后该用户所有请求将被拒绝。`,
                    )}
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      u.status === 'disabled' ? 'bg-red-50 text-dc-red' : 'bg-green-50 text-dc-green'
                    }`}
                  >
                    {u.status === 'disabled' ? 'disabled' : 'active'}
                  </button>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-dc-text-3">{u.invite_code ?? '—'}</td>
                <td className="px-4 py-3 text-xs text-dc-text-3">{new Date(u.created_at).toLocaleDateString('zh-CN')}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    disabled={busy === u.id}
                    onClick={() => repair(u.id)}
                    className="p-1.5 text-dc-text-3 hover:text-dc-accent"
                    title="重建 new-api 计费映射"
                  >
                    {busy === u.id ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
                  </button>
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
