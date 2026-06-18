// 我的器具 API（/v1/equipment）。对话里 AI 自动保存与此页手动维护共用同一份数据。
import { apiFetch } from './client'

export interface EquipmentProfile {
  id: string
  brew_method?: string | null   // 冲煮方式（下拉枚举）
  dripper?: string | null       // 滤杯 / 冲煮器具（自由文本）
  grinder?: string | null
  filter_media?: string | null
  water?: string | null
  label?: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface EquipmentInput {
  brew_method?: string
  dripper?: string
  grinder?: string
  filter_media?: string
  water?: string
  label?: string
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

// 设为默认器具套；后端自动取消其余套的默认（单默认不变量）。
export function setDefaultEquipment(id: string): Promise<EquipmentProfile> {
  return updateEquipment(id, { is_default: true })
}
