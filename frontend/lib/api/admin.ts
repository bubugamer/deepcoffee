// 管理后台 API 封装（/v1/admin/*，全部需要 admin 身份的 Bearer token）。
// 形状与后端 schema 一一对应：app/schemas/auth.py、proposal.py、candidate.py、entity.py。
import { apiFetch } from './client'

// ── Types ───────────────────────────────────────────────────────────────────

export interface AdminStats {
  user_count: number
  active_invite_count: number
  pending_proposal_count: number
  pending_candidate_count: number
  active_entity_count: number
}

export interface InviteCodeInfo {
  code: string
  status: string // active | used | revoked
  expires_at?: string | null
  note?: string | null
  used_by?: string | null
  used_by_email?: string | null
  used_at?: string | null
  created_at: string
}

export interface AdminUserInfo {
  id: string
  email?: string | null
  display_name?: string | null
  plan: string
  role: string
  status: string
  created_at: string
  invite_code?: string | null
  invited_at?: string | null
  ai_used: number
  ai_total: number | null
  ai_remaining: number | null
  quota_custom: boolean
}

export interface AdminAuditEvent {
  created_at: string
  actor_email?: string | null
  action: string
  before_value?: string | null
  after_value?: string | null
  reason?: string | null
}

export interface ProposalAuditEntry {
  action: string
  actor_id: string
  note?: string | null
  created_at: string
}

export interface Proposal {
  id: string
  entity_type: string
  title: string
  payload: Record<string, unknown>
  source_input?: string | null
  trace_id?: string | null
  proposer_id: string
  status: 'pending' | 'approved' | 'rejected' | 'applied'
  reviewer_note?: string | null
  applied_entity_id?: string | null
  applied_markdown_path?: string | null
  created_at: string
  updated_at: string
  audit: ProposalAuditEntry[]
}

export interface CandidateFact {
  id: string
  entity_type: string
  fact_type?: string | null
  title: string
  payload: Record<string, unknown>
  source_scope: string
  source_table?: string | null
  source_record_id?: string | null
  source_user_id?: string | null
  source_input?: string | null
  status: string // pending_review | promoted | rejected
  proposed_entity_id?: string | null
  proposal_id?: string | null
  reviewer_note?: string | null
  trace_id?: string | null
  created_at: string
  updated_at: string
}

export interface PublicEntity {
  id: string
  entity_type: string
  canonical_name: string
  normalized_name: string
  scope: string
  status: string
  summary?: string | null
  created_from: string
  created_at: string
  updated_at: string
  detail?: Record<string, unknown> | null
}

export interface KnowledgeReloadResult {
  article_count: number
  public_article_count: number
  indexable_article_count: number
  scanned_markdown_count: number
  category_count: number
  entity_count: number
  reloaded_at: string
}

// ── Stats / Invites / Users ─────────────────────────────────────────────────

export function getAdminStats(): Promise<AdminStats> {
  return apiFetch('/admin/stats')
}

export function listInvites(status?: string): Promise<InviteCodeInfo[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiFetch(`/admin/invites${q}`)
}

export function createInvites(body: { count: number; note?: string; expires_at?: string }): Promise<InviteCodeInfo[]> {
  return apiFetch('/admin/invites', { method: 'POST', body: JSON.stringify(body) })
}

export function revokeInvite(code: string): Promise<InviteCodeInfo> {
  return apiFetch(`/admin/invites/${encodeURIComponent(code)}/revoke`, { method: 'POST' })
}

export function listAdminUsers(page = 1, pageSize = 20): Promise<AdminUserInfo[]> {
  return apiFetch(`/admin/users?page=${page}&page_size=${pageSize}`)
}

export function updateAdminUser(
  userId: string,
  body: { plan?: string; role?: string; status?: string },
): Promise<AdminUserInfo> {
  return apiFetch(`/admin/users/${encodeURIComponent(userId)}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export function updateAdminUserQuota(
  userId: string,
  body: { monthly_limit?: number | null; used_this_month?: number; reason?: string },
): Promise<AdminUserInfo> {
  return apiFetch(`/admin/users/${encodeURIComponent(userId)}/quota`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function getAdminUserAudit(userId: string, page = 1, pageSize = 50): Promise<AdminAuditEvent[]> {
  return apiFetch(`/admin/users/${encodeURIComponent(userId)}/audit?page=${page}&page_size=${pageSize}`)
}

// ── Review: proposals / candidates / entities ──────────────────────────────

export function listProposals(params?: { status?: string; entity_type?: string; page?: number }): Promise<Proposal[]> {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.entity_type) q.set('entity_type', params.entity_type)
  if (params?.page) q.set('page', String(params.page))
  const qs = q.toString()
  return apiFetch(`/admin/proposals${qs ? `?${qs}` : ''}`)
}

export function approveProposal(id: string, note?: string): Promise<Proposal> {
  return apiFetch(`/admin/proposals/${id}/approve`, { method: 'POST', body: JSON.stringify({ reviewer_note: note ?? null }) })
}

export function rejectProposal(id: string, note?: string): Promise<Proposal> {
  return apiFetch(`/admin/proposals/${id}/reject`, { method: 'POST', body: JSON.stringify({ reviewer_note: note ?? null }) })
}

export function markProposalApplied(id: string, body?: { applied_markdown_path?: string; reviewer_note?: string }): Promise<Proposal> {
  return apiFetch(`/admin/proposals/${id}/mark-applied`, { method: 'POST', body: JSON.stringify(body ?? {}) })
}

export function listCandidates(params?: { status?: string; entity_type?: string; page?: number }): Promise<CandidateFact[]> {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.entity_type) q.set('entity_type', params.entity_type)
  if (params?.page) q.set('page', String(params.page))
  const qs = q.toString()
  return apiFetch(`/admin/candidates${qs ? `?${qs}` : ''}`)
}

export function promoteCandidate(id: string, note?: string): Promise<{ candidate_id: string; proposal_id: string; status: string }> {
  return apiFetch(`/admin/candidates/${id}/promote`, { method: 'POST', body: JSON.stringify({ reviewer_note: note ?? null }) })
}

export function rejectCandidate(id: string, note?: string): Promise<CandidateFact> {
  return apiFetch(`/admin/candidates/${id}/reject`, { method: 'POST', body: JSON.stringify({ reviewer_note: note ?? null }) })
}

export function listEntities(params?: { entity_type?: string; status?: string }): Promise<PublicEntity[]> {
  const q = new URLSearchParams()
  if (params?.entity_type) q.set('entity_type', params.entity_type)
  if (params?.status) q.set('status', params.status)
  const qs = q.toString()
  return apiFetch(`/admin/entities${qs ? `?${qs}` : ''}`)
}

// ── Knowledge ops ───────────────────────────────────────────────────────────

export function reloadKnowledge(): Promise<KnowledgeReloadResult> {
  return apiFetch('/admin/knowledge/reload', { method: 'POST' })
}
