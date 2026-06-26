import type { BeanRecommendedParams, BrewEvaluation } from '@/types'

export function formatBrewSeconds(seconds?: number): string | undefined {
  if (seconds === undefined || seconds === null) return undefined
  const mins = Math.floor(seconds / 60)
  const secs = String(seconds % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

export function recommendedParamRows(params?: BeanRecommendedParams | null): [string, string][] {
  if (!params) return []
  return [
    ['滤杯', params.device],
    ['研磨', params.grinder && params.grind_setting
      ? `${params.grinder} ${params.grind_setting}`
      : (params.grinder ?? params.grind_setting)],
    ['豆量', params.dose_g !== undefined ? `${params.dose_g} g` : undefined],
    ['水量', params.water_ml !== undefined ? `${params.water_ml} ml` : undefined],
    ['水温', params.water_temp_c !== undefined ? `${params.water_temp_c}°C` : undefined],
    ['粉水比', params.ratio],
    ['时间', formatBrewSeconds(params.brew_time_seconds)],
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
