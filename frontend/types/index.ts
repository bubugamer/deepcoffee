// ── Brew Records ──────────────────────────────────────────────────────────
export interface BrewEvaluationItem {
  score?: number        // integer 1–5
  description?: string
}

export interface BrewEvaluation {
  overall?: BrewEvaluationItem
  aroma?: BrewEvaluationItem
  flavor?: BrewEvaluationItem
  aftertaste?: BrewEvaluationItem
  acidity?: BrewEvaluationItem
  body?: BrewEvaluationItem
  balance?: BrewEvaluationItem
}

export interface BrewStep {
  time_seconds: number
  action: string
  water_ml?: number
  note?: string
}

export interface BrewRecord {
  id: string
  user_id: string
  source_type: string
  bean_card_id?: string | null
  record_type?: string
  is_user_visible?: boolean
  bean_name?: string
  origin?: string
  roaster?: string
  process?: string
  varietal?: string
  device?: string
  grinder?: string
  grind_setting?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time?: string
  brew_time_seconds?: number
  brew_steps: BrewStep[]
  evaluation?: BrewEvaluation
  notes?: string
  raw_input?: string
  recap?: string
  suggestions: string[]
  trace_id?: string
  created_at: string
  updated_at: string
}

export interface BrewDraft {
  bean_card_id?: string
  bean_name?: string
  origin?: string
  roaster?: string
  process?: string
  varietal?: string
  device?: string
  grinder?: string
  grind_setting?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time?: string
  brew_time_seconds?: number
  brew_steps: BrewStep[]
  evaluation?: BrewEvaluation
  notes?: string
}

export interface BrewComparisonItem {
  id: string
  date: string
  bean_name?: string
  device?: string
  grinder?: string
  grind_setting?: string
  dose_g?: number
  water_ml?: number
  ratio?: string
  ratio_value?: number
  water_temp_c?: number
  brew_time_seconds?: number
  overall_score?: number
  active: boolean
}

// ── Bean Cards ─────────────────────────────────────────────────────────────
export interface FlavorAxis {
  label: string
  value?: number | null
}

export interface BeanFlavor {
  notes: string[]
  source: 'roaster' | 'default' | 'user'
  scale_max: number
  axes: FlavorAxis[]
}

export interface BeanDraft {
  name?: string
  roaster_name?: string
  roaster_product_name?: string
  coffee_source_name?: string
  green_bean_merchant_name?: string
  green_bean_product_name?: string
  origin_name?: string
  process_name?: string
  varietal_names?: string[]
  flavor?: BeanFlavor
  private_notes?: string
}

export interface BeanRecommendedParams {
  record_id: string
  record_type?: string
  device?: string
  grinder?: string
  grind_setting?: string
  dose_g?: number
  water_ml?: number
  water_temp_c?: number
  ratio?: string
  ratio_value?: number
  brew_time_seconds?: number
}

export interface Bean {
  bean_id: string
  name: string
  roaster?: string | null
  roaster_product?: string | null
  coffee_source?: string | null
  green_bean_merchant?: string | null
  green_bean_product?: string | null
  origin?: string | null
  process?: string | null
  varietal: string[]
  flavor: BeanFlavor
  private_notes?: string | null
  recommended_record_id?: string | null
  recommended_params?: BeanRecommendedParams | null
  avg_score?: number | null
  record_count: number
  created_at: string
  updated_at: string
}

export interface BeanParseResponse {
  draft: BeanDraft
  confidence: number
  low_confidence_fields: string[]
  clarification?: string | null
  trace_id: string
}

export interface BeanConfirmResponse {
  bean_id: string
  trace_id: string
}

export interface RecommendParamsResponse {
  recommended_params: BeanRecommendedParams
  recommended_record_id: string
  trace_id: string
}

// ── Recommend Params (多轮) ─────────────────────────────────────────────────
// needs_input: 还需用户补充器具等信息；completed: 已生成建议；fallback: 信息不足给默认兜底
export type RecommendParamsStatus = 'needs_input' | 'completed' | 'fallback'

export interface RecommendEquipment {
  brew_method?: string | null
  grinder?: string | null
  filter_media?: string | null
  water?: string | null
}

export interface RecommendationParams {
  device?: string | null
  grinder?: string | null
  filter?: string | null
  dose_g?: number | null
  water_ml?: number | null
  water_temp_c?: number | null
  ratio?: string | null
  grind_setting?: string | null
  brew_time_seconds?: number | null
  notes?: string | null
}

export interface RecommendParamsTurnResponse {
  status: RecommendParamsStatus
  intent?: string | null
  assistant_message: string
  session_id: string
  equipment: RecommendEquipment
  missing_fields: string[]
  recommendation?: RecommendationParams | null
  recommended_record_id?: string | null
  source: 'model' | 'local'
  trace_id: string
}

// ── Knowledge Base ─────────────────────────────────────────────────────────
export interface TocItem {
  id: string
  title: string
  level: number
}

export interface RelatedArticle {
  slug: string
  title: string
}

export interface ArticleSection {
  id: string
  heading: string
  body?: string
  items?: string[]
}

export interface Article {
  slug: string
  cat: string
  title: string
  desc: string
  category?: string
  category_key?: string
  summary?: string
  updated_at?: string
  path?: string
  updated?: string
  toc?: TocItem[]
  related?: RelatedArticle[]
}

export interface ArticleDetail extends Article {
  markdown?: string
  sections: ArticleSection[]
}

export interface KBCategory {
  key: string
  label: string
  count: number
  sub: string
  href: string
}

// ── User ───────────────────────────────────────────────────────────────────
export interface UserProfile {
  id: string
  email?: string
  display_name?: string
  plan: string
  role?: string          // 'user' | 'admin' — 管理后台入口与守卫依据
  status?: string        // 'active' | 'disabled'
  invite_bound?: boolean // false 时弹「补填邀请码」（后端门禁 invite_required 的前置提示）
  timezone: string
  unit_system: string    // 'metric' | 'imperial'
  created_at: string
}

export interface UserQuota {
  plan: string
  balance: number
  ai_used: number
  ai_total: number | null  // null = unlimited (Pro)
  ai_remaining: number | null
  reset_at?: string | null
  features: string[]
}

// GET /v1/billing/plans — 套餐价格/额度一律读接口渲染，不在前端写死
export interface BillingPlan {
  id: string
  name: string
  price: number
  currency: string
  token_limit: number | null
  request_limit: number | null   // null = 无限次（Pro）
  period: string
  features: string[]
}

// ── AI Chat ────────────────────────────────────────────────────────────────
export interface DraftField {
  label: string
  value: string
  lowConf?: boolean
}

// ── Coffea 统一聊天 (POST /v1/coffea/messages) ──────────────────────────────
export interface CoffeaAttachment {
  type: string              // 'image'
  ref?: string | null
  url?: string | null
  data_url?: string | null  // data:image/...;base64,... —— vision 模型只收 base64
  image_base64?: string | null
  mime_type?: string | null
  note?: string | null
}

export type ActionStatus = 'done' | 'degraded' | 'pending' | 'failed'

export interface ActionResult {
  type: string
  status: ActionStatus
  source?: string | null
  output?: Record<string, unknown> | null
  message?: string | null
}

export interface CoffeaSessionState {
  active_bean_id?: string | null
  active_recipe_id?: string | null
  active_brew_id?: string | null
  active_equipment_id?: string | null
}

export interface CoffeaMessageRequest {
  message: string
  session_id?: string | null
  attachments?: CoffeaAttachment[]
}

export interface CoffeaMessageResponse {
  session_id: string
  primary_intent: string
  secondary_intents: string[]
  actions: Record<string, unknown>[]
  results: ActionResult[]
  state: CoffeaSessionState
  reply?: string | null
  should_answer_directly: boolean
  source: 'model' | 'local' | 'mixed'
  trace_id: string
}

// web_verify 动作 output.sources[] 的引用条目
export interface WebVerifySource {
  title?: string
  url?: string
  published_at?: string
  time?: string
}
