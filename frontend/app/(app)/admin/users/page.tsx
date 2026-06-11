'use client'
// 用户管理：纯展示列表 + 「操作」列（详情 = 查看与编辑弹窗；修改历史 = 审计记录弹窗）。
// 自我降级/自禁用由后端 cannot_modify_self 拦截，弹窗内直接透出报错信息。
import { useCallback, useEffect, useState } from 'react'
import { Loader2, ChevronLeft, ChevronRight, X } from 'lucide-react'
import {
  listAdminUsers, updateAdminUser, updateAdminUserQuota, getAdminUserAudit,
  type AdminUserInfo, type AdminAuditEvent,
} from '@/lib/api/admin'
import { ApiError } from '@/lib/api/client'

const PAGE_SIZE = 20

const AUDIT_ACTION_LABEL: Record<string, string> = {
  plan_change: '套餐',
  role_change: '角色',
  status_change: '状态',
  quota_limit_change: '月额度上限',
  usage_adjust: '已用次数',
}

function displayLimit(user: AdminUserInfo): string {
  if (user.ai_total === null) return '无限'
  return String(user.ai_total)
}

function displayRemaining(user: AdminUserInfo): string {
  if (user.ai_remaining === null) return '无限'
  return String(user.ai_remaining)
}

function mutateErrorText(err: unknown): string {
  if (err instanceof ApiError && err.code === 'cannot_modify_self') return '不能对自己执行该操作'
  return err instanceof Error ? err.message : '操作失败'
}

// ── 详情（查看 + 编辑）弹窗 ──────────────────────────────
function UserDetailModal({
  user, onClose, onUpdated,
}: {
  user: AdminUserInfo
  onClose: () => void
  onUpdated: (next: AdminUserInfo) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [monthlyLimit, setMonthlyLimit] = useState(
    user.quota_custom && user.ai_total !== null ? String(user.ai_total) : '',
  )
  const [used, setUsed] = useState(String(user.ai_used))
  const [reason, setReason] = useState('')

  async function mutate(body: { plan?: string; role?: string; status?: string }, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(true)
    setError('')
    try {
      onUpdated(await updateAdminUser(user.id, body))
    } catch (err) {
      setError(mutateErrorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function saveQuota() {
    const monthlyText = monthlyLimit.trim()
    const usedText = used.trim()
    const monthly_limit = monthlyText === '' ? null : Number(monthlyText)
    const used_this_month = usedText === '' ? undefined : Number(usedText)
    if ((monthly_limit !== null && (!Number.isInteger(monthly_limit) || monthly_limit < 0))
      || (used_this_month !== undefined && (!Number.isInteger(used_this_month) || used_this_month < 0))) {
      setError('额度和已用次数必须是 0 或正整数')
      return
    }
    setBusy(true)
    setError('')
    try {
      const next = await updateAdminUserQuota(user.id, {
        monthly_limit,
        used_this_month,
        reason: reason.trim() || undefined,
      })
      onUpdated(next)
      setReason('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '调整失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="dc-card w-full max-w-lg max-h-[85vh] overflow-y-auto p-5 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-dc-text-1">{user.email ?? user.id}</h3>
            <p className="font-mono text-[11px] text-dc-text-3 mt-0.5">{user.id}</p>
          </div>
          <button onClick={onClose} className="p-1 text-dc-text-3 hover:text-dc-text-1"><X size={16} /></button>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-dc-text-2">
          <div><span className="text-dc-text-3">注册邀请码：</span><span className="font-mono">{user.invite_code ?? '—'}</span></div>
          <div><span className="text-dc-text-3">注册时间：</span>{new Date(user.created_at).toLocaleDateString('zh-CN')}</div>
          <div><span className="text-dc-text-3">本月已用：</span>{user.ai_used} / {displayLimit(user)}</div>
          <div><span className="text-dc-text-3">剩余：</span>{displayRemaining(user)}（{user.quota_custom ? '自定义额度' : '套餐默认'}）</div>
        </div>

        {error && <div className="text-xs text-dc-red">{error}</div>}

        <div className="border-t border-dc-border pt-4 space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-dc-text-3 w-16">套餐</label>
            <select
              value={user.plan}
              disabled={busy}
              onChange={e => mutate({ plan: e.target.value })}
              className="text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white"
            >
              <option value="basic">basic</option>
              <option value="pro">pro</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-dc-text-3 w-16">角色</label>
            <select
              value={user.role}
              disabled={busy}
              onChange={e => mutate({ role: e.target.value },
                e.target.value === 'admin' ? `将 ${user.email ?? user.id} 设为管理员？` : `撤销 ${user.email ?? user.id} 的管理员权限？`)}
              className="text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white"
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-dc-text-3 w-16">状态</label>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              user.status === 'disabled' ? 'bg-red-50 text-dc-red' : 'bg-green-50 text-dc-green'
            }`}>{user.status}</span>
            <button
              disabled={busy}
              onClick={() => mutate(
                { status: user.status === 'disabled' ? 'active' : 'disabled' },
                user.status === 'disabled'
                  ? `恢复 ${user.email ?? user.id}？`
                  : `禁用 ${user.email ?? user.id}？禁用后该用户所有请求将被拒绝。`,
              )}
              className="text-xs text-dc-accent hover:underline disabled:opacity-50"
            >
              {user.status === 'disabled' ? '恢复账号' : '禁用账号'}
            </button>
          </div>
        </div>

        <div className="border-t border-dc-border pt-4 space-y-2">
          <div className="text-xs font-medium text-dc-text-2">额度调整</div>
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-dc-text-3">已用</label>
            <input
              type="number" min={0} inputMode="numeric" value={used} disabled={busy}
              onChange={e => setUsed(e.target.value)}
              className="w-24 text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white"
            />
            <span className="text-xs text-dc-text-3">/</span>
            <input
              type="number" min={0} inputMode="numeric" value={monthlyLimit} disabled={busy}
              placeholder={`${displayLimit(user)}（留空 = 套餐默认）`}
              onChange={e => setMonthlyLimit(e.target.value)}
              className="w-44 text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white"
            />
          </div>
          <input
            value={reason} disabled={busy}
            onChange={e => setReason(e.target.value)}
            placeholder="调整原因（会写入修改历史）"
            className="w-full text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white"
          />
          <button
            disabled={busy}
            onClick={saveQuota}
            className="btn-primary text-xs py-1.5 px-4 disabled:opacity-50"
          >
            {busy ? <Loader2 size={13} className="animate-spin inline" /> : '保存额度'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 修改历史弹窗 ─────────────────────────────────────────
function UserAuditModal({ user, onClose }: { user: AdminUserInfo; onClose: () => void }) {
  const [events, setEvents] = useState<AdminAuditEvent[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getAdminUserAudit(user.id)
      .then(setEvents)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [user.id])

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="dc-card w-full max-w-xl max-h-[85vh] overflow-y-auto p-5 space-y-3"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-dc-text-1">修改历史</h3>
            <p className="text-xs text-dc-text-3 mt-0.5">{user.email ?? user.id}</p>
          </div>
          <button onClick={onClose} className="p-1 text-dc-text-3 hover:text-dc-text-1"><X size={16} /></button>
        </div>

        {error && <div className="text-xs text-dc-red">{error}</div>}
        {events === null && !error && (
          <div className="py-6 text-center text-dc-text-3 text-sm">
            <Loader2 size={15} className="animate-spin inline mr-2" />加载中…
          </div>
        )}
        {events?.length === 0 && (
          <div className="py-6 text-center text-dc-text-3 text-sm">暂无修改记录</div>
        )}
        {events && events.length > 0 && (
          <div className="divide-y divide-dc-border">
            {events.map((e, i) => (
              <div key={i} className="py-2.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-dc-text-1 font-medium">
                    {AUDIT_ACTION_LABEL[e.action] ?? e.action}：
                    <span className="text-dc-text-3">{e.before_value ?? '—'}</span>
                    <span className="mx-1 text-dc-text-3">→</span>
                    <span className="text-dc-accent">{e.after_value ?? '—'}</span>
                  </span>
                  <span className="text-dc-text-3 whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
                <div className="mt-0.5 text-dc-text-3">
                  操作人：{e.actor_email ?? '—'}
                  {e.reason ? ` · 原因：${e.reason}` : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── 列表页 ───────────────────────────────────────────────
export default function AdminUsersPage() {
  const [items, setItems] = useState<AdminUserInfo[] | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [detailUser, setDetailUser] = useState<AdminUserInfo | null>(null)
  const [auditUser, setAuditUser] = useState<AdminUserInfo | null>(null)

  const refresh = useCallback(() => {
    setError(null)
    listAdminUsers(page, PAGE_SIZE)
      .then(setItems)
      .catch(err => setError(err instanceof Error ? err.message : '加载失败'))
  }, [page])

  useEffect(() => { refresh() }, [refresh])

  function handleUpdated(next: AdminUserInfo) {
    setItems(current => current?.map(item => item.id === next.id ? next : item) ?? current)
    setDetailUser(next)
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
              <th className="px-4 py-3 font-medium">本月用量</th>
              <th className="px-4 py-3 font-medium">注册邀请码</th>
              <th className="px-4 py-3 font-medium">注册时间</th>
              <th className="px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dc-border">
            {items === null && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-dc-text-3">
                <Loader2 size={15} className="animate-spin inline mr-2" />加载中…
              </td></tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-dc-text-3">暂无用户</td></tr>
            )}
            {items?.map(u => (
              <tr key={u.id} className={u.status === 'disabled' ? 'opacity-50' : ''}>
                <td className="px-4 py-3 text-dc-text-1 max-w-52">
                  <div className="truncate">{u.email ?? u.id}</div>
                  <div className="font-mono text-[11px] text-dc-text-3 truncate">{u.id}</div>
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-2">{u.plan}</td>
                <td className="px-4 py-3 text-xs text-dc-text-2">{u.role}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    u.status === 'disabled' ? 'bg-red-50 text-dc-red' : 'bg-green-50 text-dc-green'
                  }`}>{u.status}</span>
                </td>
                <td className="px-4 py-3 text-xs text-dc-text-2 whitespace-nowrap">
                  {u.ai_used} / {displayLimit(u)}
                  <span className="text-dc-text-3 ml-2">剩余 {displayRemaining(u)}</span>
                  <span className="text-dc-text-3 ml-2">{u.quota_custom ? '自定义' : '套餐默认'}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-dc-text-3">{u.invite_code ?? '—'}</td>
                <td className="px-4 py-3 text-xs text-dc-text-3">{new Date(u.created_at).toLocaleDateString('zh-CN')}</td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <button onClick={() => setDetailUser(u)} className="text-xs text-dc-accent hover:underline">详情</button>
                  <button onClick={() => setAuditUser(u)} className="text-xs text-dc-accent hover:underline ml-3">修改历史</button>
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

      {detailUser && (
        <UserDetailModal
          user={detailUser}
          onClose={() => setDetailUser(null)}
          onUpdated={handleUpdated}
        />
      )}
      {auditUser && <UserAuditModal user={auditUser} onClose={() => setAuditUser(null)} />}
    </div>
  )
}
