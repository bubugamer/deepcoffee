import type { Bean, BeanComponent, BeanRecommendedParams, BrewEvaluation } from '@/types'
import type { ComboOption } from '@/components/Combobox'
import type { BeanEntityCatalog, EntityCatalogItem } from '@/lib/api/beans'

export function formatBrewSeconds(seconds?: number): string | undefined {
  if (seconds === undefined || seconds === null) return undefined
  const mins = Math.floor(seconds / 60)
  const secs = String(seconds % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

// 展示口径与「冲煮记录」对齐：同字段、同叫法、同顺序（冲煮方式 → 器具 → 研磨 → 过滤介质 → 用水 → 用量 → 粉水比 → 水温 → 时间）。
export function recommendedParamRows(params?: BeanRecommendedParams | null): [string, string][] {
  if (!params) return []
  return [
    ['冲煮方式', params.brew_method],
    ['冲煮器具', params.device],
    ['研磨', params.grinder && params.grind_setting
      ? `${params.grinder} ${params.grind_setting}`
      : (params.grinder ?? params.grind_setting)],
    ['过滤介质', params.filter_media],
    ['用水', params.water],
    ['豆量', params.dose_g !== undefined ? `${params.dose_g} g` : undefined],
    ['水量', params.water_ml !== undefined ? `${params.water_ml} ml` : undefined],
    ['粉水比', params.ratio],
    ['水温', params.water_temp_c !== undefined ? `${params.water_temp_c}°C` : undefined],
    ['冲煮时间', formatBrewSeconds(params.brew_time_seconds)],
  ].filter(([, value]) => value) as [string, string][]
}

// ── 豆卡配色（按处理法）──────────────────────────────────────────────
// 系统约定处理法存中文（解析时 washed→水洗 等），但库里仍有未归一的英文，
// 故配色匹配中英双语都认。拼配（多豆源、处理法可能多种）统一走 other 冷白主题。

export interface CardTheme {
  frontBg: string
  backBg: string
  textMain: string
  textSub: string
  accent: string
  tagBg: string
}

export type ProcessFamily = 'washed' | 'natural' | 'honey' | 'anaerobic' | 'other'

// 优先级：anaerobic > honey > washed > natural > other
// （"pulped natural" / "anaerobic natural" 要先命中蜜 / 厌氧，避免被 natural 抢走）
const PROCESS_KEYWORDS: [ProcessFamily, string[]][] = [
  ['anaerobic', ['anaerobic', 'carbonic', 'maceration', 'cm', '厌氧', '二氧化碳', '浸渍', '发酵']],
  ['honey', ['honey', 'miel', 'pulped natural', '蜜']],
  ['washed', ['washed', 'wash', 'wet', '水洗', '湿处理', '湿刨']],
  ['natural', ['natural', 'dry', 'sun', '日晒', '自然', '干处理']],
]

export function processFamily(process?: string | null): ProcessFamily {
  const p = (process ?? '').toLowerCase()
  if (!p.trim()) return 'other'
  for (const [family, keywords] of PROCESS_KEYWORDS) {
    if (keywords.some((kw) => p.includes(kw))) return family
  }
  return 'other'
}

const THEMES: Record<ProcessFamily, CardTheme> = {
  washed: {
    frontBg: 'linear-gradient(145deg, #DCEEFB 0%, #B6DCF5 100%)',
    backBg: 'linear-gradient(145deg, #B6DCF5 0%, #8FC4EC 100%)',
    textMain: '#0B2E4F', textSub: '#2C5B82', accent: '#1565C0', tagBg: '#A6CFEC',
  },
  natural: {
    frontBg: 'linear-gradient(145deg, #FFE7D0 0%, #FFC79A 100%)',
    backBg: 'linear-gradient(145deg, #FFC79A 0%, #FBA56A 100%)',
    textMain: '#5A2400', textSub: '#9A4D14', accent: '#E8590C', tagBg: '#FBC79A',
  },
  honey: {
    frontBg: 'linear-gradient(145deg, #FFF3C9 0%, #FCE08A 100%)',
    backBg: 'linear-gradient(145deg, #FCE08A 0%, #F6CC52 100%)',
    textMain: '#4A3500', textSub: '#8A6A12', accent: '#C8920A', tagBg: '#F7DA8A',
  },
  anaerobic: {
    frontBg: 'linear-gradient(145deg, #F3E1F0 0%, #E4C0E2 100%)',
    backBg: 'linear-gradient(145deg, #E4C0E2 0%, #D29ECF 100%)',
    textMain: '#3E1140', textSub: '#6E3A6E', accent: '#9C27B0', tagBg: '#DDB4DA',
  },
  // 冷调近白：和站点暖奶油明显拉开；未知处理法 + 拼配（多豆源）都走这套。
  other: {
    frontBg: 'linear-gradient(145deg, #F7F9FB 0%, #EAEEF3 100%)',
    backBg: 'linear-gradient(145deg, #EAEEF3 0%, #DBE2EA 100%)',
    textMain: '#28303A', textSub: '#5A6573', accent: '#4A5A6E', tagBg: '#DCE3EB',
  },
}

export function getCardTheme(process?: string | null, opts?: { blend?: boolean }): CardTheme {
  if (opts?.blend) return THEMES.other
  return THEMES[processFamily(process)]
}

// ── 风味标签 emoji ────────────────────────────────────────────────
// 两层：① AI 解析时给每个风味词配的 note_emojis（覆盖冷门新词）；② 内置词库兜底。
// 顺序从具体到笼统，命中即返回；都不中返回 null（不强配错图标）。
const FLAVOR_EMOJI: [string, string[]][] = [
  ['🌵', ['prickly pear', '仙人掌', '刺梨']],
  ['🌹', ['rose', '玫瑰']],
  ['🌸', ['floral', 'flower', 'blossom', 'jasmine', '花香', '花', '茉莉']],
  ['🍋', ['lemon', '柠檬']],
  ['🍊', ['citrus', 'orange', 'grapefruit', 'bergamot', 'mandarin', 'tangerine', '柑', '橘', '橙', '柚', '佛手柑']],
  ['🍓', ['strawberry', '草莓']],
  ['🫐', ['blueberry', 'berry', 'blackberry', 'raspberry', 'cranberry', '蓝莓', '莓']],
  // 荔枝/龙眼无专属 emoji，用最接近的「小红圆果」🍒 代替（🥭 是芒果，不能混用）。
  ['🍒', ['cherry', 'lychee', 'longan', '樱桃', '车厘子', '荔枝', '龙眼']],
  ['🍑', ['peach', 'apricot', 'plum', 'nectarine', '桃', '杏', '李', '梅']],
  ['🥭', ['mango', 'papaya', '芒果', '木瓜']],
  ['🍍', ['pineapple', 'passion', 'guava', 'tropical', '菠萝', '凤梨', '百香果', '番石榴', '热带']],
  ['🥝', ['kiwi', '猕猴桃', '奇异果']],
  ['🍈', ['melon', 'cantaloupe', 'honeydew', '哈密瓜', '蜜瓜', '瓜']],
  ['🍎', ['apple', '苹果']],
  ['🍐', ['pear', 'quince', '梨']],
  ['🍇', ['grape', 'wine', 'raisin', 'muscat', 'fermented', 'boozy', '葡萄', '提子', '酒', '红酒']],
  ['🥥', ['coconut', '椰']],
  ['🍫', ['chocolate', 'cocoa', 'cacao', 'dark chocolate', '巧克力', '可可']],
  ['🌰', ['nut', 'almond', 'hazelnut', 'peanut', 'walnut', 'pecan', '坚果', '杏仁', '榛', '花生', '核桃']],
  ['🍮', ['caramel', 'toffee', 'custard', '焦糖', '太妃', '布丁']],
  ['🍯', ['honey', '蜂蜜', '蜜']],
  ['🍬', ['sugar', 'syrup', 'molasses', 'sweet', 'candy', '红糖', '枫糖', '糖浆', '糖', '甜']],
  ['🌿', ['vanilla', 'herbal', 'mint', 'herb', '香草', '薄荷', '草本']],
  ['🧂', ['spice', 'cinnamon', 'clove', 'cardamom', 'pepper', 'ginger', 'nutmeg', '香料', '肉桂', '丁香', '胡椒', '姜', '豆蔻']],
  ['🍵', ['tea', 'black tea', 'green tea', 'earl grey', '红茶', '绿茶', '茶']],
  ['🍞', ['bread', 'biscuit', 'toast', 'cookie', 'graham', '面包', '饼干', '吐司', '烤']],
  ['🌾', ['malt', 'grain', 'cereal', 'wheat', 'barley', '麦芽', '谷物', '麦']],
  ['🧈', ['butter', 'cream', 'creamy', 'milk', 'dairy', '黄油', '奶油', '牛奶', '乳']],
  ['🪵', ['tobacco', 'leather', 'cedar', 'woody', 'wood', 'earthy', '烟草', '皮革', '雪松', '木', '泥土']],
  ['🥃', ['rum', 'whiskey', 'whisky', 'brandy', 'bourbon', '朗姆', '威士忌', '白兰地']],
]

export function flavorEmoji(note: string, noteEmojis?: Record<string, string> | null): string | null {
  const fromAi = noteEmojis?.[note]
  if (fromAi) return fromAi
  const n = note.toLowerCase()
  for (const [emoji, keywords] of FLAVOR_EMOJI) {
    if (keywords.some((kw) => n.includes(kw))) return emoji
  }
  return null
}

// ── 豆源（component）编辑草稿 + 与后端 BeanComponent 互转 ─────────────
// 表单里每条豆源用字符串草稿编辑（品种用逗号分隔），保存时转回 BeanComponent。
// 新建页与详情页编辑共用，避免两套逻辑漂移。
export interface ComponentDraft {
  origin_name: string
  coffee_source_name: string
  green_bean_merchant_name: string
  green_bean_product_name: string
  process_name: string
  varietalsText: string
  altitude_text: string
  harvest_date_text: string
  share_text: string
  notes: string
}

export const EMPTY_COMPONENT_DRAFT: ComponentDraft = {
  origin_name: '', coffee_source_name: '', green_bean_merchant_name: '', green_bean_product_name: '',
  process_name: '', varietalsText: '', altitude_text: '', harvest_date_text: '', share_text: '', notes: '',
}

function trimOrNull(text: string): string | null {
  const t = text.trim()
  return t ? t : null
}

export function splitVarietals(text: string): string[] {
  return text.split(/[，,]/).map((s) => s.trim()).filter(Boolean)
}

export function componentToDraft(c: BeanComponent): ComponentDraft {
  return {
    origin_name: c.origin_name ?? '',
    coffee_source_name: c.coffee_source_name ?? '',
    green_bean_merchant_name: c.green_bean_merchant_name ?? '',
    green_bean_product_name: c.green_bean_product_name ?? '',
    process_name: c.process_name ?? '',
    varietalsText: (c.varietal_names ?? []).join('，'),
    altitude_text: c.altitude_text ?? '',
    harvest_date_text: c.harvest_date_text ?? '',
    share_text: c.share_text ?? '',
    notes: c.notes ?? '',
  }
}

export function draftToComponent(c: ComponentDraft): BeanComponent {
  return {
    origin_name: trimOrNull(c.origin_name),
    coffee_source_name: trimOrNull(c.coffee_source_name),
    green_bean_merchant_name: trimOrNull(c.green_bean_merchant_name),
    green_bean_product_name: trimOrNull(c.green_bean_product_name),
    process_name: trimOrNull(c.process_name),
    varietal_names: splitVarietals(c.varietalsText),
    altitude_text: trimOrNull(c.altitude_text),
    harvest_date_text: trimOrNull(c.harvest_date_text),
    share_text: trimOrNull(c.share_text),
    notes: trimOrNull(c.notes),
  }
}

export function componentHasContent(c: ComponentDraft): boolean {
  return [
    c.origin_name, c.coffee_source_name, c.green_bean_merchant_name, c.green_bean_product_name,
    c.process_name, c.varietalsText, c.altitude_text, c.harvest_date_text, c.share_text, c.notes,
  ].some((v) => v.trim().length > 0)
}

export function normalizedComponentsForSave(components: ComponentDraft[]): ComponentDraft[] {
  return components.filter(componentHasContent)
}

// 至少一条有效豆源；填了内容的豆源必须有产地 + 处理法。返回错误文案或 null。
export function validateComponentsForSave(components: ComponentDraft[]): string | null {
  const active = normalizedComponentsForSave(components)
  if (active.length === 0) return '请在「豆源」里至少填写一条产地和处理法。'
  const invalid = components.findIndex((c) => componentHasContent(c) && (!c.origin_name.trim() || !c.process_name.trim()))
  if (invalid >= 0) {
    const c = components[invalid]
    const missing = [!c.origin_name.trim() ? '产地' : '', !c.process_name.trim() ? '处理法' : ''].filter(Boolean).join('、')
    return `请补全豆源 ${invalid + 1} 的${missing}。`
  }
  return null
}

// ── 豆卡录入下拉：实体驱动（公共实体目录 + 别名）∪ 用户已有豆卡值 ───────────
// 目录来自后端 /beans/entity-catalog（getBeanEntityCatalog），即生产库真实、已审核的实体。
// 别名（含英文/简称）只用于「搜索匹配」与「去重」，下拉里只展示规范名，绝不把英文变体单列。
const normSuggest = (s: string) => s.toLowerCase().replace(/\s+/g, '').trim()

// 实体目录项 → combobox 选项（value/label = 规范名，aliases 仅用于搜索/去重）。
export function entityCatalogOptions(items: EntityCatalogItem[]): ComboOption[] {
  return items.map((i) => ({ value: i.name, label: i.name, aliases: i.aliases ?? [] }))
}

// 目录选项 ∪ 用户已有值：已有值若命中目录规范名或其任一别名（忽略大小写/空格），视作同一别名、不再单列。
function mergeWithCatalog(base: ComboOption[], existing: Iterable<string>): ComboOption[] {
  const known = new Set<string>()
  for (const o of base) {
    known.add(normSuggest(o.label))
    for (const a of o.aliases ?? []) known.add(normSuggest(a))
  }
  const out = [...base]
  const seen = new Set<string>()
  for (const v of existing) {
    const key = normSuggest(v)
    if (!key || known.has(key) || seen.has(key)) continue
    seen.add(key)
    out.push({ value: v, label: v })
  }
  return out
}

export interface BeanFieldSuggestions {
  processes: ComboOption[]
  origins: ComboOption[]
  varietals: ComboOption[]
  roasters: ComboOption[]
}

// 下拉/输入建议：烘焙商 / 处理法 / 产地 / 品种 = 公共实体目录（带别名）∪ 已有值（去重）。
export function beanFieldSuggestions(beans: Bean[], catalog: BeanEntityCatalog): BeanFieldSuggestions {
  const processes = new Set<string>()
  const origins = new Set<string>()
  const varietals = new Set<string>()
  const roasters = new Set<string>()
  for (const bean of beans) {
    for (const c of bean.bean_components ?? []) {
      if (c.process_name) processes.add(c.process_name)
      if (c.origin_name) origins.add(c.origin_name)
      for (const v of c.varietal_names ?? []) if (v) varietals.add(v)
    }
    if (bean.process) processes.add(bean.process)
    if (bean.origin) origins.add(bean.origin)
    for (const v of bean.varietal ?? []) if (v) varietals.add(v)
    if (bean.roaster) roasters.add(bean.roaster)
  }
  return {
    processes: mergeWithCatalog(entityCatalogOptions(catalog.process), processes),
    roasters: mergeWithCatalog(entityCatalogOptions(catalog.roaster), roasters),
    origins: mergeWithCatalog(entityCatalogOptions(catalog.origin), origins),
    varietals: mergeWithCatalog(entityCatalogOptions(catalog.varietal), varietals),
  }
}

// ── 评分维度标签（背面卡「用户评价」用）──────────────────────────────
export const RATING_LABELS: [keyof BrewEvaluation, string][] = [
  ['overall', '总评'],
  ['flavor', '风味'],
  ['aroma', '香气'],
  ['acidity', '酸度'],
  ['body', '醇厚度'],
  ['aftertaste', '余韵'],
  ['balance', '平衡'],
]
