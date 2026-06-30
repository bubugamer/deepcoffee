'use client'

import { Plus, Trash2 } from 'lucide-react'
import type { FlavorAxis } from '@/types'
import { softValidate, type FieldKind } from '@/lib/validate'
import {
  EMPTY_COMPONENT_DRAFT,
  splitVarietals,
  type BeanFieldSuggestions,
  type ComponentDraft,
} from '@/lib/beans'
import { Combobox, type ComboOption } from './Combobox'

// 受控豆卡核心表单：豆卡信息 + 豆源（含处理法/产地/品种下拉）+ 风味。
// 新建页（mode=create）与详情页编辑（mode=edit）共用，state/保存由各自页面持有。
export interface BeanFormValue {
  fields: Record<string, string>
  components: ComponentDraft[]
  flavorNotesText: string
  axes: FlavorAxis[]
}

export const BEAN_PRODUCT_FIELDS: { key: string; label: string; required?: boolean; unit?: string; kind?: FieldKind; placeholder?: string }[] = [
  { key: 'roaster_name', label: '烘焙商', required: true },
  { key: 'roaster_product_name', label: '烘焙商产品 / 批次名' },
  { key: 'roast_date_text', label: '烘焙日期', kind: 'date', placeholder: '如 2026/05/18' },
  { key: 'net_weight_text', label: '净含量', unit: '克', kind: 'number', placeholder: '如 250' },
]

export function emptyBeanFormValue(): BeanFormValue {
  return { fields: {}, components: [{ ...EMPTY_COMPONENT_DRAFT }], flavorNotesText: '', axes: [] }
}

function toOptions(values: string[]): ComboOption[] {
  return values.map((v) => ({ value: v, label: v }))
}

export function BeanField({ label, value, onChange, required, unit, kind, placeholder }: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  unit?: string
  kind?: FieldKind
  placeholder?: string
}) {
  const warning = softValidate(kind, value)
  return (
    <label className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">
        {label}{unit && `（${unit}）`}{required && <span className="text-dc-red"> *</span>}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? '未填写'}
        className={`dc-input text-sm py-1.5 ${warning ? 'border-dc-yellow' : ''}`}
      />
      {warning && <p className="text-xs text-dc-yellow mt-1">{warning}</p>}
    </label>
  )
}

function ComboField({ label, required, value, options, placeholder, onChange, onSelect }: {
  label: string
  required?: boolean
  value: string
  options: string[]
  placeholder?: string
  onChange: (value: string) => void
  onSelect?: (value: string) => void
}) {
  return (
    <div className="block">
      <span className="text-xs text-dc-text-3 mb-1 block">
        {label}{required && <span className="text-dc-red"> *</span>}
      </span>
      <Combobox
        options={toOptions(options)}
        value={value}
        placeholder={placeholder ?? `输入或选择${label}`}
        onInput={onChange}
        onSelect={onSelect ?? onChange}
      />
    </div>
  )
}

// 交互式评分点（风味维度强度）
function Dots({ value, max = 5, onSelect }: { value?: number | null; max?: number; onSelect: (v: number | null) => void }) {
  const safeMax = Math.max(1, Math.round(max))
  const safeValue = Math.max(0, Math.min(safeMax, Math.round(value ?? 0)))
  return (
    <div className="flex gap-1">
      {Array.from({ length: safeMax }, (_, index) => (
        <span
          key={index}
          onClick={() => onSelect(index + 1 === safeValue ? null : index + 1)}
          className={`w-2.5 h-2.5 rounded-full border cursor-pointer transition-colors ${
            index < safeValue ? 'bg-dc-accent border-dc-accent' : 'border-dc-border hover:border-dc-accent'
          }`}
        />
      ))}
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="dc-card p-5">
      <h2 className="section-title mb-1">{title}</h2>
      {hint && <p className="text-xs text-dc-text-3 mb-4">{hint}</p>}
      {!hint && <div className="mb-4" />}
      {children}
    </div>
  )
}

export function BeanForm({ value, onChange, suggestions }: {
  value: BeanFormValue
  onChange: (value: BeanFormValue) => void
  suggestions: BeanFieldSuggestions
}) {
  function setField(key: string, text: string) {
    onChange({ ...value, fields: { ...value.fields, [key]: text } })
  }
  function setComponents(components: ComponentDraft[]) {
    onChange({ ...value, components })
  }
  function setComponent(index: number, patch: Partial<ComponentDraft>) {
    setComponents(value.components.map((c, i) => (i === index ? { ...c, ...patch } : c)))
  }
  function appendVarietal(index: number, varietal: string) {
    const current = splitVarietals(value.components[index].varietalsText)
    if (!current.includes(varietal)) current.push(varietal)
    setComponent(index, { varietalsText: current.join('，') })
  }

  return (
    <div className="space-y-5">
      <Section title="豆卡信息">
        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
          {BEAN_PRODUCT_FIELDS.map(({ key, label, required, unit, kind, placeholder }) => (
            <BeanField
              key={key}
              label={label}
              required={required}
              unit={unit}
              kind={kind}
              placeholder={placeholder}
              value={value.fields[key] ?? ''}
              onChange={(text) => setField(key, text)}
            />
          ))}
        </div>
      </Section>

      <Section title="豆源（单豆 1 条，拼配可加多条）">
        {value.components.length === 0 ? (
          <p className="text-sm text-dc-text-3 mb-3">点「添加豆源」填写产地、处理法、品种等信息。</p>
        ) : (
          <div className="space-y-4 mb-4">
            {value.components.map((component, index) => (
              <div key={index} className="border border-dc-border rounded-lg p-3">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-sm font-medium text-dc-text-1">豆源 {index + 1}</div>
                  {value.components.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setComponents(value.components.filter((_, i) => i !== index))}
                      className="text-dc-red hover:bg-dc-red/5 rounded-md p-1"
                      aria-label="删除豆源"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                  <ComboField label="产地" required value={component.origin_name} options={suggestions.origins} onChange={(v) => setComponent(index, { origin_name: v })} />
                  <BeanField label="生产者 / 庄园 / 处理站" value={component.coffee_source_name} onChange={(v) => setComponent(index, { coffee_source_name: v })} />
                  <ComboField label="处理法" required value={component.process_name} options={suggestions.processes} onChange={(v) => setComponent(index, { process_name: v })} />
                  <ComboField label="品种" value={component.varietalsText} options={suggestions.varietals} placeholder="输入或选择品种，多个用逗号分隔" onChange={(v) => setComponent(index, { varietalsText: v })} onSelect={(v) => appendVarietal(index, v)} />
                  <BeanField label="生豆商 / 进口商" value={component.green_bean_merchant_name} onChange={(v) => setComponent(index, { green_bean_merchant_name: v })} />
                  <BeanField label="生豆商产品" value={component.green_bean_product_name} onChange={(v) => setComponent(index, { green_bean_product_name: v })} />
                  <BeanField label="海拔" unit="米" kind="number" placeholder="如 1800" value={component.altitude_text} onChange={(v) => setComponent(index, { altitude_text: v })} />
                  <BeanField label="采收期" unit="年" kind="year" placeholder="如 2024 或 2023-2024" value={component.harvest_date_text} onChange={(v) => setComponent(index, { harvest_date_text: v })} />
                  <BeanField label="占比 / 说明" value={component.share_text} onChange={(v) => setComponent(index, { share_text: v })} />
                </div>
                <label className="block mt-3">
                  <span className="text-xs text-dc-text-3 mb-1 block">备注</span>
                  <textarea
                    value={component.notes}
                    onChange={(e) => setComponent(index, { notes: e.target.value })}
                    className="dc-input text-sm min-h-[64px] resize-none leading-relaxed"
                  />
                </label>
              </div>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => setComponents([...value.components, { ...EMPTY_COMPONENT_DRAFT }])}
          className="btn-secondary text-sm px-3 py-2 inline-flex items-center gap-1.5"
        >
          <Plus size={14} />
          添加豆源
        </button>
      </Section>

      <Section title="风味信息">
        <div className="mb-4">
          <BeanField
            label="风味标签"
            value={value.flavorNotesText}
            onChange={(text) => onChange({ ...value, flavorNotesText: text })}
            placeholder="例如：花香，荔枝，红酒"
          />
        </div>
        <div className="space-y-3">
          {value.axes.map((axis, index) => (
            <div key={index} className="grid sm:grid-cols-[1fr_auto_auto] gap-3 items-center">
              <input
                value={axis.label}
                onChange={(e) => onChange({ ...value, axes: value.axes.map((a, i) => (i === index ? { ...a, label: e.target.value } : a)) })}
                placeholder="维度名称，例如 酸"
                className="dc-input text-sm py-1.5"
              />
              <Dots value={axis.value} onSelect={(v) => onChange({ ...value, axes: value.axes.map((a, i) => (i === index ? { ...a, value: v } : a)) })} />
              <button
                type="button"
                onClick={() => onChange({ ...value, axes: value.axes.filter((_, i) => i !== index) })}
                className="text-dc-red hover:bg-dc-red/5 rounded-md p-1 justify-self-start sm:justify-self-auto"
                aria-label="删除风味维度"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => onChange({ ...value, axes: [...value.axes, { label: '', value: null }] })}
          className="btn-secondary text-sm px-3 py-2 inline-flex items-center gap-1.5 mt-4"
        >
          <Plus size={14} />
          添加维度
        </button>
      </Section>
    </div>
  )
}
