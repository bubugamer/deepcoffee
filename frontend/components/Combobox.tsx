'use client'

import { useEffect, useRef, useState } from 'react'

export interface ComboOption {
  value: string
  label: string
  // 关联别名（规范名的简写/中英/型号等），仅用于模糊搜索匹配，不展示。
  aliases?: string[]
}

// 归一化：忽略大小写与空格，中英文都按字符串子串比。
function norm(s: string): string {
  return s.toLowerCase().replace(/\s+/g, '').trim()
}

/**
 * 可搜索下拉：输入即按 label + aliases 模糊过滤，浮层列出匹配的规范名；
 * 选建议回传该项 value（onSelect），自由键入回传文本（onInput，天然作自定义值兜底）。
 * 不持有「自定义/已选」状态，交由调用方按各自语义（器具单值 / 豆子 id+自定义）维护。
 */
export function Combobox({
  options,
  value,
  placeholder,
  highlight = false,
  autoFocus = false,
  maxLength,
  onInput,
  onSelect,
}: {
  options: ComboOption[]
  value: string
  placeholder?: string
  highlight?: boolean
  autoFocus?: boolean
  maxLength?: number
  onInput: (text: string) => void
  onSelect: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  const q = norm(value)
  // 当前文本恰好等于某个已选项的 label（用户没在改）→ 列出全部供改选；否则按输入过滤。
  const exact = options.some((o) => o.label === value)
  const filtered = !q || exact
    ? options
    : options.filter((o) => norm(o.label).includes(q) || (o.aliases ?? []).some((a) => norm(a).includes(q)))

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  function choose(option: ComboOption) {
    onSelect(option.value)
    setOpen(false)
  }

  const fieldCls = `dc-input text-sm py-1.5 ${highlight ? 'border-dc-yellow bg-dc-yellow-bg/50' : ''}`

  return (
    <div ref={boxRef} className="relative">
      <input
        value={value}
        placeholder={placeholder}
        autoFocus={autoFocus}
        maxLength={maxLength}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        onChange={(e) => { onInput(e.target.value); setOpen(true); setActive(0) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { setOpen(true); return }
          if (!open) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
          else if (e.key === 'Enter') { if (filtered[active]) { e.preventDefault(); choose(filtered[active]) } }
          else if (e.key === 'Escape') setOpen(false)
        }}
        className={fieldCls}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full max-h-60 overflow-auto rounded-lg border border-dc-border bg-white shadow-lg py-1">
          {filtered.map((option, i) => (
            <li key={option.value}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(option)}
                onMouseEnter={() => setActive(i)}
                className={`block w-full text-left px-3 py-1.5 text-sm text-dc-text-1 hover:bg-dc-subtle ${i === active ? 'bg-dc-subtle' : ''}`}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
