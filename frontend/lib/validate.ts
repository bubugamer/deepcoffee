// 表单字段的「基本格式」软校验：只在用户填了、且明显不符时给一句提示，
// 不拦截保存（强度见各表单）。空值（选填）一律视为通过。
export type FieldKind = 'number' | 'date' | 'year' | 'time' | 'ratio'

const RULES: Record<FieldKind, { test: RegExp; hint: string }> = {
  number: { test: /^\d+(\.\d+)?$/, hint: '请输入数字' },
  date: { test: /^\d{4}[/-]\d{1,2}[/-]\d{1,2}$/, hint: '日期格式如 2026/05/18' },
  year: { test: /^\d{4}([/-]\d{4})?$/, hint: '年份如 2024 或 2023-2024' },
  time: { test: /^(\d+[:：]\d{1,2}|\d+)$/, hint: '如 2:30 或 150（秒）' },
  ratio: { test: /^1[:：]\d+(\.\d+)?$/, hint: '如 1:15' },
}

// 返回 null = 通过（含空值）；返回字符串 = 给用户的软提示。
export function softValidate(kind: FieldKind | undefined, value: string): string | null {
  if (!kind) return null
  const v = value.trim()
  if (!v) return null
  return RULES[kind].test.test(v) ? null : RULES[kind].hint
}
