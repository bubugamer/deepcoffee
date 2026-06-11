// 我的器具 API（/v1/equipment）。对话里 AI 自动保存与此页手动维护共用同一份数据。
import { apiFetch } from './client'

export interface EquipmentProfile {
  id: string
  brew_method?: string | null
  grinder?: string | null
  filter_media?: string | null
  water?: string | null
  label?: string | null
  created_at: string
  updated_at: string
}

export interface EquipmentInput {
  brew_method?: string
  grinder?: string
  filter_media?: string
  water?: string
  label?: string
}

export function listEquipment(): Promise<EquipmentProfile[]> {
  return apiFetch('/equipment')
}

export function createEquipment(body: EquipmentInput): Promise<EquipmentProfile> {
  return apiFetch('/equipment', { method: 'POST', body: JSON.stringify(body) })
}

export function updateEquipment(id: string, body: EquipmentInput): Promise<EquipmentProfile> {
  return apiFetch(`/equipment/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export function deleteEquipment(id: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/equipment/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
