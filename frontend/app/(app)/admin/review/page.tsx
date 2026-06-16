'use client'
// 内容审核工作台：提案 / 候选事实 / 实体库 三个 tab，全部来自 /v1/admin/* 真实数据。
// 替代原 mock 版 EntityReviewWorkbench（entity-review-fixtures 已删除）。
import { Suspense, useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Loader2, CheckCircle2, XCircle, ArrowUpCircle, X } from 'lucide-react'
import {
  listProposals, approveProposal, rejectProposal, markProposalApplied,
  listCandidates, promoteCandidate, rejectCandidate, mergeCandidate,
  listEntities, listEntityDuplicates, mergeEntity, renameEntity,
  type Proposal, type CandidateFact, type PublicEntity, type EntityDuplicatesResponse,
} from '@/lib/api/admin'

type Tab = 'proposals' | 'candidates' | 'entities'

const tabs: { value: Tab; label: string }[] = [
  { value: 'proposals',  label: '提案' },
  { value: 'candidates', label: '候选事实' },
  { value: 'entities',   label: '实体库' },
]

const statusBadge: Record<string, string> = {
  pending: 'bg-yellow-50 text-dc-yellow',
  pending_review: 'bg-yellow-50 text-dc-yellow',
  approved: 'bg-green-50 text-dc-green',
  applied: 'bg-green-50 text-dc-green',
  active: 'bg-green-50 text-dc-green',
  promoted: 'bg-dc-subtle text-dc-text-3',
  rejected: 'bg-red-50 text-dc-red',
}

function Badge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${statusBadge[status] ?? 'bg-dc-subtle text-dc-text-3'}`}>
      {status}
    </span>
  )
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  return (
    <pre className="bg-dc-subtle rounded-lg p-3 text-xs text-dc-text-2 overflow-x-auto whitespace-pre-wrap break-all">
      {JSON.stringify(payload, null, 2)}
    </pre>
  )
}

function ReviewInner() {
  const searchParams = useSearchParams()
  const initialTab = (searchParams.get('tab') as Tab) || 'proposals'
  const [tab, setTab] = useState<Tab>(tabs.some(t => t.value === initialTab) ? initialTab : 'proposals')

  const [statusFilter, setStatusFilter] = useState('')
  const [proposals, setProposals] = useState<Proposal[] | null>(null)
  const [candidates, setCandidates] = useState<CandidateFact[] | null>(null)
  const [entities, setEntities] = useState<PublicEntity[] | null>(null)
  const [dupes, setDupes] = useState<EntityDuplicatesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [detail, setDetail] = useState<Proposal | CandidateFact | null>(null)
  const [note, setNote] = useState('')

  const refresh = useCallback(() => {
    setError(null)
    const fail = (err: unknown) => setError(err instanceof Error ? err.message : '加载失败')
    if (tab === 'proposals') {
      setProposals(null)
      listProposals(statusFilter ? { status: statusFilter } : undefined).then(setProposals).catch(fail)
    } else if (tab === 'candidates') {
      setCandidates(null)
      listCandidates(statusFilter ? { status: statusFilter } : undefined).then(setCandidates).catch(fail)
    } else {
      setEntities(null)
      setDupes(null)
      listEntities(statusFilter ? { status: statusFilter } : undefined).then(setEntities).catch(fail)
      // 清理建议（疑似重复 + 待规范主名）只看 active，不随状态筛选变化。
      listEntityDuplicates().then(setDupes).catch(() => setDupes(null))
    }
  }, [tab, statusFilter])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => { setDetail(null); setNote('') }, [tab])

  async function act(id: string, action: () => Promise<unknown>) {
    setBusy(id)
    setError(null)
    try {
      await action()
      setDetail(null)
      setNote('')
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(null)
    }
  }

  // 阶段 4：把整组重复实体并入选中的「保留」实体；改名走 prompt 收单一主名。
  function mergeGroup(keepId: string, members: PublicEntity[]) {
    const others = members.filter(m => m.id !== keepId)
    if (others.length === 0) return
    act(keepId, async () => {
      for (const m of others) await mergeEntity(m.id, keepId)
    })
  }
  function renamePrompt(en: PublicEntity) {
    const next = window.prompt(`把「${en.canonical_name}」规范成单一主名：`, en.canonical_name)
    if (next && next.trim() && next.trim() !== en.canonical_name) {
      act(en.id, () => renameEntity(en.id, next.trim()))
    }
  }

  const statusOptions: Record<Tab, string[]> = {
    proposals: ['pending', 'approved', 'rejected', 'applied'],
    candidates: ['pending_review', 'promoted', 'rejected'],
    entities: ['active', 'archived'],
  }

  const loading = (tab === 'proposals' && proposals === null)
    || (tab === 'candidates' && candidates === null)
    || (tab === 'entities' && entities === null)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1 bg-dc-subtle rounded-lg p-1">
          {tabs.map(t => (
            <button
              key={t.value}
              onClick={() => { setTab(t.value); setStatusFilter('') }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                tab === t.value ? 'bg-white text-dc-text-1 shadow-sm' : 'text-dc-text-3 hover:text-dc-text-1'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="text-xs border border-dc-border rounded-md px-2 py-1.5 bg-white text-dc-text-2"
        >
          <option value="">全部状态</option>
          {statusOptions[tab].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {error && <div className="text-sm text-dc-red">{error}</div>}
      {loading && (
        <div className="flex items-center text-dc-text-3 text-sm py-8 justify-center">
          <Loader2 size={15} className="animate-spin mr-2" />加载中…
        </div>
      )}

      {/* ── 提案列表 ── */}
      {tab === 'proposals' && proposals && (
        <div className="dc-card divide-y divide-dc-border">
          {proposals.length === 0 && <div className="px-5 py-8 text-center text-sm text-dc-text-3">没有符合条件的提案</div>}
          {proposals.map(p => (
            <button
              key={p.id}
              onClick={() => { setDetail(p); setNote('') }}
              className="w-full px-5 py-3.5 flex items-center gap-4 text-left hover:bg-dc-subtle/50"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-dc-text-1 truncate">{p.title}</div>
                <div className="text-xs text-dc-text-3 mt-0.5">{p.entity_type} · {new Date(p.created_at).toLocaleString('zh-CN')}</div>
              </div>
              <Badge status={p.status} />
            </button>
          ))}
        </div>
      )}

      {/* ── 候选事实列表 ── */}
      {tab === 'candidates' && candidates && (
        <div className="dc-card divide-y divide-dc-border">
          {candidates.length === 0 && <div className="px-5 py-8 text-center text-sm text-dc-text-3">没有符合条件的候选事实</div>}
          {candidates.map(c => (
            <button
              key={c.id}
              onClick={() => { setDetail(c); setNote('') }}
              className="w-full px-5 py-3.5 flex items-center gap-4 text-left hover:bg-dc-subtle/50"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-dc-text-1 truncate">{c.title}</div>
                <div className="text-xs text-dc-text-3 mt-0.5">{c.entity_type}{c.fact_type ? ` · ${c.fact_type}` : ''} · {new Date(c.created_at).toLocaleString('zh-CN')}</div>
              </div>
              <Badge status={c.status} />
            </button>
          ))}
        </div>
      )}

      {/* ── 实体库（含阶段 4 清理建议） ── */}
      {tab === 'entities' && entities && (
        <div className="space-y-4">
          {dupes && (dupes.groups.length > 0 || dupes.mixed_names.length > 0) && (
            <div className="dc-card p-4 space-y-3">
              <div className="text-sm font-bold text-dc-text-1">清理建议</div>
              {dupes.groups.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-dc-yellow">疑似重复：点你想保留的那一个，组内其余并入它</div>
                  {dupes.groups.map((g, gi) => (
                    <div key={gi} className="border border-dc-border rounded-lg p-2.5 space-y-1.5">
                      <div className="text-xs text-dc-text-3">
                        {g.reason === 'form' ? '写法相同' : '缩写/全称'} · {g.entities[0]?.entity_type}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {g.entities.map(e => (
                          <button
                            key={e.id}
                            disabled={busy !== null}
                            onClick={() => mergeGroup(e.id, g.entities)}
                            title="保留它，其余并入"
                            className="px-2.5 py-1 text-xs border border-dc-border rounded-md hover:border-dc-accent-hi disabled:opacity-60"
                          >
                            {e.canonical_name} <span className="text-dc-accent">· 保留</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {dupes.mixed_names.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-dc-yellow">待规范主名（中英混写，建议收成单一主名）</div>
                  <div className="flex flex-wrap gap-1.5">
                    {dupes.mixed_names.map(en => (
                      <button
                        key={en.id}
                        disabled={busy !== null}
                        onClick={() => renamePrompt(en)}
                        className="px-2.5 py-1 text-xs border border-dc-border rounded-md hover:border-dc-accent-hi disabled:opacity-60"
                      >
                        {en.canonical_name} <span className="text-dc-accent">· 规范</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="dc-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-dc-text-3 border-b border-dc-border">
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">来源</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">摘要</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dc-border">
              {entities.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-dc-text-3">暂无实体</td></tr>
              )}
              {entities.map(en => (
                <tr key={en.id}>
                  <td className="px-4 py-3 text-dc-text-1 font-medium">{en.canonical_name}</td>
                  <td className="px-4 py-3 text-xs text-dc-text-3">{en.entity_type}</td>
                  <td className="px-4 py-3 text-xs text-dc-text-3">{en.created_from}</td>
                  <td className="px-4 py-3"><Badge status={en.status} /></td>
                  <td className="px-4 py-3 text-xs text-dc-text-3 max-w-60 truncate">{en.summary ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* ── 详情侧滑（提案/候选共用） ── */}
      {detail && (
        <div className="fixed inset-0 z-50" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/30" />
          <div
            className="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-xl overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-dc-border px-5 py-4 flex items-center justify-between">
              <h3 className="text-sm font-bold text-dc-text-1 truncate pr-4">{detail.title}</h3>
              <button onClick={() => setDetail(null)} className="p-1 text-dc-text-3 hover:text-dc-text-1"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-2 text-xs text-dc-text-3">
                <Badge status={detail.status} />
                <span>{detail.entity_type}</span>
                <span>·</span>
                <span>{new Date(detail.created_at).toLocaleString('zh-CN')}</span>
              </div>

              {detail.source_input && (
                <div>
                  <div className="text-xs font-medium text-dc-text-3 mb-1">原始输入</div>
                  <div className="bg-dc-subtle rounded-lg p-3 text-xs text-dc-text-2 whitespace-pre-wrap">{detail.source_input}</div>
                </div>
              )}

              <div>
                <div className="text-xs font-medium text-dc-text-3 mb-1">Payload</div>
                <PayloadView payload={detail.payload} />
              </div>

              {detail.reviewer_note && (
                <div>
                  <div className="text-xs font-medium text-dc-text-3 mb-1">审核备注</div>
                  <div className="text-sm text-dc-text-2">{detail.reviewer_note}</div>
                </div>
              )}

              {'audit' in detail && detail.audit.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-dc-text-3 mb-1">审计记录</div>
                  <div className="space-y-1">
                    {detail.audit.map((a, i) => (
                      <div key={i} className="text-xs text-dc-text-3">
                        {new Date(a.created_at).toLocaleString('zh-CN')} · {a.action}{a.note ? ` · ${a.note}` : ''}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 操作区：仅待审状态展示 */}
              {(detail.status === 'pending' || detail.status === 'pending_review' || detail.status === 'approved') && (
                <div className="border-t border-dc-border pt-4 space-y-3">
                  {!('audit' in detail) && detail.similar_entities && detail.similar_entities.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-dc-yellow">疑似已有实体（点「并入」避免重复建档）：</div>
                      {detail.similar_entities.map(e => (
                        <button
                          key={e.id}
                          disabled={busy === detail.id}
                          onClick={() => act(detail.id, () => mergeCandidate(detail.id, e.id, note.trim() || undefined))}
                          className="w-full text-left px-3 py-2 border border-dc-border rounded-lg text-sm hover:border-dc-accent-hi flex items-center justify-between gap-2 disabled:opacity-60"
                        >
                          <span className="truncate text-dc-text-1">{e.canonical_name}</span>
                          <span className="text-xs text-dc-accent whitespace-nowrap">并入 →</span>
                        </button>
                      ))}
                    </div>
                  )}
                  <textarea
                    className="dc-input text-sm"
                    rows={2}
                    placeholder="审核备注（可选）"
                    value={note}
                    onChange={e => setNote(e.target.value)}
                  />
                  <div className="flex gap-2">
                    {/* 提案：pending → approve/reject；approved → mark-applied */}
                    {'audit' in detail && detail.status === 'pending' && (
                      <>
                        <button
                          disabled={busy === detail.id}
                          onClick={() => act(detail.id, () => approveProposal(detail.id, note.trim() || undefined))}
                          className="flex-1 btn-primary py-2.5 text-sm flex items-center justify-center gap-1.5 disabled:opacity-60"
                        >
                          <CheckCircle2 size={14} /> 通过
                        </button>
                        <button
                          disabled={busy === detail.id}
                          onClick={() => act(detail.id, () => rejectProposal(detail.id, note.trim() || undefined))}
                          className="flex-1 py-2.5 text-sm border border-dc-border rounded-lg text-dc-red hover:bg-red-50 flex items-center justify-center gap-1.5 disabled:opacity-60"
                        >
                          <XCircle size={14} /> 驳回
                        </button>
                      </>
                    )}
                    {'audit' in detail && detail.status === 'approved' && (
                      <button
                        disabled={busy === detail.id}
                        onClick={() => act(detail.id, () => markProposalApplied(detail.id, { reviewer_note: note.trim() || undefined }))}
                        className="flex-1 btn-primary py-2.5 text-sm flex items-center justify-center gap-1.5 disabled:opacity-60"
                      >
                        <CheckCircle2 size={14} /> 标记已应用
                      </button>
                    )}
                    {/* 候选：pending_review → promote/reject */}
                    {!('audit' in detail) && detail.status === 'pending_review' && (
                      <>
                        <button
                          disabled={busy === detail.id}
                          onClick={() => act(detail.id, () => promoteCandidate(detail.id, note.trim() || undefined))}
                          className="flex-1 btn-primary py-2.5 text-sm flex items-center justify-center gap-1.5 disabled:opacity-60"
                        >
                          <ArrowUpCircle size={14} /> 升为提案
                        </button>
                        <button
                          disabled={busy === detail.id}
                          onClick={() => act(detail.id, () => rejectCandidate(detail.id, note.trim() || undefined))}
                          className="flex-1 py-2.5 text-sm border border-dc-border rounded-lg text-dc-red hover:bg-red-50 flex items-center justify-center gap-1.5 disabled:opacity-60"
                        >
                          <XCircle size={14} /> 驳回
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminReviewPage() {
  return (
    <Suspense fallback={null}>
      <ReviewInner />
    </Suspense>
  )
}
