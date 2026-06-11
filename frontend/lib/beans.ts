import type { BeanRecommendedParams } from '@/types'

export function formatBrewSeconds(seconds?: number): string | undefined {
  if (seconds === undefined || seconds === null) return undefined
  const mins = Math.floor(seconds / 60)
  const secs = String(seconds % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

export function recommendedParamRows(params?: BeanRecommendedParams | null): [string, string][] {
  if (!params) return []
  return [
    ['器具', params.device],
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
