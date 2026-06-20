'use client'

import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Bean, BrewEvaluation, BrewEvaluationItem, BrewRecord, BrewRecordFormInput, BrewStep } from '@/types'
import type { EquipmentCategory, EquipmentProfile } from '@/lib/api/equipment'

const BREW_METHODS = ['滤杯冲煮', '意式', '法压壶', '爱乐压', '浸泡式', '摩卡壶', '虹吸壶', '冷萃']
const CUSTOM = '__custom__'

const RATING_FIELDS: { key: keyof BrewEvaluation; label: string }[] = [
  { key: 'overall', label: '总评' },
  { key: 'aroma', label: '香气' },
  { key: 'flavor', label: '风味' },
  { key: 'aftertaste', label: '余韵' },
  { key: 'acidity', label: '酸质' },
  { key: 'body', label: '触感' },
  { key: 'balance', label: '平衡度' },
]

const EQUIPMENT_LABELS: Record<EquipmentCategory, string> = {
  brewer: '冲煮器具',
  grinder: '磨豆机',
  filter_media: '过滤介质',
  water: '用水',
}

export interface BrewRecordFormSubmit {
  payload: BrewRecordFormInput
  equipmentToUpsert: { category: EquipmentCategory; name: string }[]
}

interface DraftState {
  beanCardId: string
  brew_method: string
  device: string
  grinder: string
  grind_setting: string
  filter_media: string
  water: string
  dose_g: string
  water_ml: string
  water_temp_c: string
  brew_time_seconds: string
  notes: string
  brew_score: number | null
  bean_rating: BrewEvaluation | null
  brew_steps: BrewStep[]
}

function fmtSeconds(seconds?: number | null) {
  if (seconds == null) return ''
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function parseTime(text: string): number | null {
  const value = text.trim()
  if (!value) return null
  const matched = value.match(/^(\d+)[:：](\d{1,2})$/)
  if (matched) return Number(matched[1]) * 60 + Number(matched[2])
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? Math.round(number) : null
}

function optionalText(value: string): string | null {
  const text = value.trim()
  return text || null
}

function optionalNumber(value: string): number | null {
  const text = value.trim()
  if (!text) return null
  const number = Number(text)
  return Number.isFinite(number) && number > 0 ? number : null
}

function ratioText(dose: string, water: string) {
  const doseNumber = optionalNumber(dose)
  const waterNumber = optionalNumber(water)
  if (!doseNumber || !waterNumber) return '自动计算'
  const ratio = Math.round((waterNumber / doseNumber) * 10) / 10
  return Number.isInteger(ratio) ? `1:${ratio}` : `1:${ratio.toFixed(1)}`
}

function initialState(record: BrewRecord | null, beans: Bean[], preferredBeanId?: string | null): DraftState {
  const beanCardId = record?.bean_card_id ?? preferredBeanId ?? ''
  const bean = beans.find((item) => item.bean_id === beanCardId)
  return {
    beanCardId,
    brew_method: record?.brew_method ?? '',
    device: record?.device ?? '',
    grinder: record?.grinder ?? '',
    grind_setting: record?.grind_setting ?? '',
    filter_media: record?.filter_media ?? '',
    water: record?.water ?? '',
    dose_g: record?.dose_g != null ? String(record.dose_g) : '',
    water_ml: record?.water_ml != null ? String(record.water_ml) : '',
    water_temp_c: record?.water_temp_c != null ? String(record.water_temp_c) : '',
    brew_time_seconds: fmtSeconds(record?.brew_time_seconds),
    notes: record?.notes ?? '',
    brew_score: record?.brew_score ?? null,
    bean_rating: record?.bean_rating ?? bean?.rating ?? null,
    brew_steps: record?.brew_steps ?? [],
  }
}

function normalizeStep(step: BrewStep): BrewStep {
  return {
    time_seconds: Math.max(0, Math.round(step.time_seconds || 0)),
    water_ml: step.water_ml && step.water_ml > 0 ? step.water_ml : undefined,
    action: step.action.trim() || '未填写',
    note: step.note?.trim() || undefined,
  }
}

function ScorePicker({ value, onChange }: { value: number | null | undefined; onChange: (value: number | null) => void }) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((score) => (
        <button
          key={score}
          type="button"
          aria-label={`${score} 分`}
          onClick={() => onChange(value === score ? null : score)}
          className={`w-3 h-3 rounded-full border transition-colors ${
            value && score <= value ? 'bg-dc-accent border-dc-accent' : 'border-dc-border bg-white hover:border-dc-accent'
          }`}
        />
      ))}
    </div>
  )
}

function setRatingScore(rating: BrewEvaluation | null, key: keyof BrewEvaluation, score: number | null): BrewEvaluation | null {
  const next: BrewEvaluation = { ...(rating ?? {}) }
  const current = next[key] as BrewEvaluationItem | undefined
  if (score == null) {
    if (current?.description) next[key] = { description: current.description }
    else delete next[key]
  } else {
    next[key] = { ...(current ?? {}), score }
  }
  return Object.keys(next).length > 0 ? next : null
}

function EquipmentSelect({
  label,
  category,
  value,
  equipment,
  onChange,
  optional = false,
}: {
  label: string
  category: EquipmentCategory
  value: string
  equipment: EquipmentProfile[]
  onChange: (value: string) => void
  optional?: boolean
}) {
  const options = useMemo(
    () => Array.from(new Set(equipment.filter((item) => item.category === category).map((item) => item.name).filter(Boolean))),
    [category, equipment],
  )
  const isCustom = value.trim() !== '' && !options.includes(value)
  const selectValue = isCustom ? CUSTOM : value
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">
        {label}{optional && <span className="ml-1">可选</span>}
      </span>
      <select
        value={selectValue}
        onChange={(event) => onChange(event.target.value === CUSTOM ? value : event.target.value)}
        className="dc-input text-sm py-1.5"
      >
        <option value="">未选择</option>
        {options.map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
        <option value={CUSTOM}>手动输入新{EQUIPMENT_LABELS[category]}</option>
      </select>
      {(selectValue === CUSTOM || isCustom) && (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="dc-input text-sm py-1.5 mt-1.5"
          placeholder={`输入${label}`}
        />
      )}
    </label>
  )
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  readOnly = false,
}: {
  label: string
  value: string
  onChange?: (value: string) => void
  placeholder?: string
  readOnly?: boolean
}) {
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">{label}</span>
      <input
        value={value}
        readOnly={readOnly}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        className={`dc-input text-sm py-1.5 ${readOnly ? 'bg-dc-subtle text-dc-text-2' : ''}`}
      />
    </label>
  )
}

export function BrewRecordForm({
  mode,
  record = null,
  beans,
  equipment,
  preferredBeanId,
  saving,
  error,
  onCancel,
  onSubmit,
}: {
  mode: 'create' | 'edit'
  record?: BrewRecord | null
  beans: Bean[]
  equipment: EquipmentProfile[]
  preferredBeanId?: string | null
  saving?: boolean
  error?: string
  onCancel: () => void
  onSubmit: (value: BrewRecordFormSubmit) => void
}) {
  const [draft, setDraft] = useState<DraftState>(() => initialState(record, beans, preferredBeanId))

  useEffect(() => {
    setDraft(initialState(record, beans, preferredBeanId))
  }, [record, beans, preferredBeanId])

  const selectedBean = beans.find((bean) => bean.bean_id === draft.beanCardId)
  const ratio = ratioText(draft.dose_g, draft.water_ml)
  const canPickBean = mode === 'create' || !record?.bean_card_id

  function set<K extends keyof DraftState>(key: K, value: DraftState[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function updateStep(index: number, patch: Partial<BrewStep>) {
    setDraft((current) => ({
      ...current,
      brew_steps: current.brew_steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    }))
  }

  function submit() {
    if (!draft.beanCardId) return
    const equipmentToUpsert = [
      { category: 'brewer' as const, name: draft.device.trim() },
      { category: 'grinder' as const, name: draft.grinder.trim() },
      { category: 'filter_media' as const, name: draft.filter_media.trim() },
      { category: 'water' as const, name: draft.water.trim() },
    ].filter((item) => item.name)

    onSubmit({
      equipmentToUpsert,
      payload: {
        bean_card_id: draft.beanCardId,
        brew_method: optionalText(draft.brew_method),
        device: optionalText(draft.device),
        grinder: optionalText(draft.grinder),
        grind_setting: optionalText(draft.grind_setting),
        filter_media: optionalText(draft.filter_media),
        water: optionalText(draft.water),
        dose_g: optionalNumber(draft.dose_g),
        water_ml: optionalNumber(draft.water_ml),
        water_temp_c: optionalNumber(draft.water_temp_c),
        brew_time_seconds: parseTime(draft.brew_time_seconds),
        brew_steps: draft.brew_steps.filter((step) => step.action.trim() || step.time_seconds || step.water_ml).map(normalizeStep),
        bean_rating: draft.bean_rating,
        brew_score: draft.brew_score,
        notes: optionalText(draft.notes),
      },
    })
  }

  return (
    <div className="dc-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3 mb-5">
        <div>
          <h2 className="section-title">{mode === 'create' ? '表单新增冲煮记录' : '编辑冲煮记录'}</h2>
          <p className="text-xs text-dc-text-3 mt-1">豆子评分属于豆卡，会同步到这款豆子的所有冲煮记录。</p>
        </div>
      </div>

      {error && <div className="mb-4 text-sm text-dc-red bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>}

      <div className="space-y-6">
        <section>
          <h3 className="text-sm font-semibold text-dc-text-1 mb-3">豆子</h3>
          {canPickBean ? (
            <label className="block">
              <span className="text-xs text-dc-text-3 mb-1 block">关联豆卡</span>
              <select
                value={draft.beanCardId}
                onChange={(event) => {
                  const beanId = event.target.value
                  const bean = beans.find((item) => item.bean_id === beanId)
                  setDraft((current) => ({ ...current, beanCardId: beanId, bean_rating: bean?.rating ?? null }))
                }}
                className="dc-input text-sm py-1.5"
              >
                <option value="">请选择豆卡</option>
                {beans.map((bean) => (
                  <option key={bean.bean_id} value={bean.bean_id}>{bean.name}</option>
                ))}
              </select>
            </label>
          ) : (
            <TextField label="关联豆卡" value={selectedBean?.name ?? record?.bean_name ?? ''} readOnly />
          )}
        </section>

        <section>
          <h3 className="text-sm font-semibold text-dc-text-1 mb-3">冲煮参数</h3>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-dc-text-3 mb-1 block">冲煮方式</span>
              <select value={draft.brew_method} onChange={(event) => set('brew_method', event.target.value)} className="dc-input text-sm py-1.5">
                <option value="">未选择</option>
                {BREW_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
              </select>
            </label>
            <EquipmentSelect label="冲煮器具" category="brewer" value={draft.device} equipment={equipment} onChange={(value) => set('device', value)} />
            <EquipmentSelect label="磨豆机" category="grinder" value={draft.grinder} equipment={equipment} onChange={(value) => set('grinder', value)} />
            <TextField label="研磨刻度" value={draft.grind_setting} onChange={(value) => set('grind_setting', value)} placeholder="例如：5.5" />
            <EquipmentSelect label="过滤介质" category="filter_media" value={draft.filter_media} equipment={equipment} onChange={(value) => set('filter_media', value)} optional />
            <EquipmentSelect label="用水" category="water" value={draft.water} equipment={equipment} onChange={(value) => set('water', value)} optional />
            <TextField label="粉量 (g)" value={draft.dose_g} onChange={(value) => set('dose_g', value)} placeholder="20" />
            <TextField label="水量 (ml)" value={draft.water_ml} onChange={(value) => set('water_ml', value)} placeholder="340" />
            <TextField label="粉水比" value={ratio} readOnly />
            <TextField label="水温 (°C)" value={draft.water_temp_c} onChange={(value) => set('water_temp_c', value)} placeholder="93" />
            <TextField label="冲煮时间" value={draft.brew_time_seconds} onChange={(value) => set('brew_time_seconds', value)} placeholder="5:00 或 300" />
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-dc-text-1 mb-3">感官记录</h3>
          <textarea
            value={draft.notes}
            onChange={(event) => set('notes', event.target.value)}
            className="dc-input text-sm min-h-24 resize-none leading-relaxed"
            placeholder="记录这杯喝起来的表现"
          />
        </section>

        <section>
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="text-sm font-semibold text-dc-text-1">冲煮阶段</h3>
            <button
              type="button"
              onClick={() => set('brew_steps', [...draft.brew_steps, { time_seconds: 0, water_ml: undefined, action: '' }])}
              className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1"
            >
              <Plus size={13} /> 添加阶段
            </button>
          </div>
          <div className="space-y-2">
            {draft.brew_steps.length === 0 ? (
              <p className="text-sm text-dc-text-3">暂无冲煮阶段，可按需添加。</p>
            ) : draft.brew_steps.map((step, index) => (
              <div key={index} className="grid grid-cols-[44px_1fr_1fr_auto] sm:grid-cols-[48px_120px_120px_1fr_auto] gap-2 items-center">
                <div className="text-xs text-dc-text-3">#{index + 1}</div>
                <input
                  value={step.time_seconds ? fmtSeconds(step.time_seconds) : ''}
                  onChange={(event) => updateStep(index, { time_seconds: parseTime(event.target.value) ?? 0 })}
                  className="dc-input text-sm py-1.5"
                  placeholder="用时"
                />
                <input
                  value={step.water_ml ?? ''}
                  onChange={(event) => updateStep(index, { water_ml: optionalNumber(event.target.value) ?? undefined })}
                  className="dc-input text-sm py-1.5"
                  placeholder="水量"
                />
                <input
                  value={step.action}
                  onChange={(event) => updateStep(index, { action: event.target.value })}
                  className="dc-input text-sm py-1.5 col-span-3 sm:col-span-1"
                  placeholder="手法"
                />
                <button
                  type="button"
                  onClick={() => set('brew_steps', draft.brew_steps.filter((_, i) => i !== index))}
                  className="p-2 text-dc-text-3 hover:text-dc-red"
                  aria-label="删除阶段"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-dc-text-1 mb-2">评分</h3>
          <div className="rounded-lg border border-dc-border bg-dc-subtle/50 px-3 py-2 text-xs text-dc-text-3 mb-3">
            豆子评分属于豆卡；本次冲煮评分只属于这条记录。
          </div>
          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
            {RATING_FIELDS.map(({ key, label }) => {
              const item = draft.bean_rating?.[key]
              return (
                <div key={key} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-dc-text-2">{label}</span>
                  <ScorePicker value={item?.score ?? null} onChange={(score) => set('bean_rating', setRatingScore(draft.bean_rating, key, score))} />
                </div>
              )
            })}
            <div className="flex items-center justify-between gap-3 sm:col-span-2 pt-2 border-t border-dc-border">
              <span className="text-sm text-dc-text-2">本次冲煮评分</span>
              <ScorePicker value={draft.brew_score} onChange={(score) => set('brew_score', score)} />
            </div>
          </div>
        </section>
      </div>

      <div className="flex gap-2 mt-6">
        <button
          type="button"
          onClick={submit}
          disabled={saving || !draft.beanCardId}
          className="btn-primary text-sm py-2 disabled:opacity-50"
        >
          {saving ? '保存中…' : '保存'}
        </button>
        <button type="button" onClick={onCancel} disabled={saving} className="btn-secondary text-sm py-2">
          取消
        </button>
      </div>
    </div>
  )
}
