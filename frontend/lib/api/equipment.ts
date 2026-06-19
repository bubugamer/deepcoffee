// 我的器具 API（/v1/equipment）。当前模型是按类别保存的单件器具库存。
import { apiFetch } from './client'

export type EquipmentCategory = 'brewer' | 'grinder' | 'filter_media' | 'water'

export interface EquipmentProfile {
  id: string
  category: EquipmentCategory
  name: string
  notes?: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface EquipmentInput {
  category?: EquipmentCategory
  name?: string
  notes?: string
  is_default?: boolean
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

// 设为该类别默认项；后端自动取消同类别其余默认。
export function setDefaultEquipment(id: string): Promise<EquipmentProfile> {
  return updateEquipment(id, { is_default: true })
}
